"""Local web tool: serves web/ on 127.0.0.1 so Chrome allows Web Bluetooth, and renders this
repo's layouts for it. Nothing listens beyond this machine, and the page itself can't reach
the network (Content-Security-Policy below). Rendering a layout fetches weather (and calendar,
haiku) exactly as a scheduled push does.

  uv run eink web                 # serve in this terminal and open Chrome (Ctrl-C stops)
  uv run eink web --background    # start it detached (hq's "Launch E-Ink Tool"); stops itself
                                  # IDLE_STOP s after the last open tab goes away
Both just open Chrome if the tool is already running.
"""
import io
import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent / "web"
THUMBS = ROOT.parent / "docs" / "images"
HOST, PORT = "127.0.0.1", 8742
URL = f"http://localhost:{PORT}/"
IDLE_STOP = 600   # s without a request (open tabs ping every 60 s) before a background server exits
LOG = ROOT.parent / ".cache" / "web.log"
last_seen = time.monotonic()
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):  # quiet: only errors
        if args and str(args[1])[:1] in "45":
            super().log_message(fmt, *args)

    def do_GET(self):
        global last_seen
        last_seen = time.monotonic()
        # Only answer to our own name: stops another site reading the agenda via DNS rebinding.
        if (self.headers.get("Host") or "").rsplit(":", 1)[0] not in (HOST, "localhost"):
            return self.send_error(403)
        url = urlparse(self.path)
        if url.path == "/api/ping":  # open tabs keep a background server alive
            return self.send_body(b"eink-tool", "text/plain")
        if url.path == "/api/layouts":
            return self.layouts()
        if url.path == "/api/render":
            return self.render(parse_qs(url.query).get("name", [""])[0])
        if url.path == "/api/thumb":
            return self.thumb(parse_qs(url.query).get("name", [""])[0])
        return super().do_GET()

    def send_body(self, body: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def layouts(self):
        from . import cli
        cfg = cli.load_config()
        rows = [{"name": n, "desc": d, "current": n == cfg["screen"]} for n, (_, d) in cli.SCREENS.items()]
        self.send_body(json.dumps(rows).encode(), "application/json")

    def thumb(self, name: str):
        """The README screenshot (docs/images/<name>.png, 2x, from tools/screenshots.py): instant, not live."""
        from . import cli
        path = THUMBS / f"{name}.png"
        if name not in cli.SCREENS or not path.is_file():
            return self.send_error(404, "no screenshot")
        self.send_body(path.read_bytes(), "image/png")

    def render(self, name: str):
        from . import cli
        from .image import preview
        cfg = cli.load_config()
        if name not in cli.SCREENS:
            return self.send_error(404, "unknown layout")
        try:
            img = preview(cli.build(name, cfg), red=True, dither=False)  # pure white/black/red
        except Exception as exc:  # network or calendar failures: tell the page
            return self.send_error(502, f"render failed: {exc}")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        self.send_body(buf.getvalue(), "image/png")


def open_browser(url: str):
    """Web Bluetooth needs Chrome or Edge (Safari has none), so prefer Chrome over the default."""
    for app in ("Google Chrome", "Microsoft Edge"):
        if Path(f"/Applications/{app}.app").exists() and shutil.which("open"):
            subprocess.run(["open", "-a", app, url], check=False)
            return
    webbrowser.open(url)


def running() -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{PORT}/api/ping", timeout=1) as r:
            return r.read() == b"eink-tool"
    except OSError:
        return False


def serve(open_page: bool = True, idle: int | None = None):
    """Serve until Ctrl-C, or with idle set, until no request has come in for that many seconds."""
    if running():
        print(f"E-ink tool already running: {URL}")
        if open_page:
            open_browser(URL)
        return
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"E-ink tool on {URL} (local only; " + (f"stops {idle // 60 or idle} {'min' if idle >= 60 else 's'} after the last tab closes)" if idle else "Ctrl-C to stop)"), flush=True)
    if idle:
        def watch():
            while time.monotonic() - last_seen < idle:
                time.sleep(15)
            print("idle, stopping", flush=True)
            server.shutdown()
        threading.Thread(target=watch, daemon=True).start()
    if open_page:
        open_browser(URL)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def launch() -> int:
    """Start the tool detached (its own session, so a job runner's cleanup can't kill it), open
    Chrome, and return: what hq's on-demand "Launch E-Ink Tool" runs."""
    if running():
        open_browser(URL)
        print(f"E-ink tool already running: {URL}")
        return 0
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a") as log:
        subprocess.Popen([sys.executable, "-m", "epd.cli", "web", "--no-open", "--idle", str(IDLE_STOP)],
                         cwd=ROOT.parent, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    for _ in range(50):
        if running():
            open_browser(URL)
            print(f"E-ink tool running: {URL} (stops {IDLE_STOP // 60} min after the last tab closes)")
            return 0
        time.sleep(0.2)
    print(f"E-ink tool failed to start; see {LOG}")
    return 1
