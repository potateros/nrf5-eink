"""nrf5-eink CLI: render a screen to PNG and/or push it to the display.

  uv run python -m epd.cli --push                      # push the screen set in config.toml
  uv run python -m epd.cli rain --preview out.png      # render a specific screen
  uv run python -m epd.cli use rain                    # switch the default screen
  uv run python -m epd.cli show rain                   # switch the default screen and push it now
  uv run python -m epd.cli list                        # available screens (* = current)
  uv run eink web                                      # local Web Bluetooth tool (--background: detached)
"""
import argparse
import csv
import datetime as dt
import asyncio
import importlib
import re
import sys
import time
import tomllib
from pathlib import Path

from PIL import Image

from .image import preview, to_planes

CONFIG = Path(__file__).resolve().parent.parent / "config.toml"

# name -> (module, description). Each module has fetch(lat, lon) and render(data, ..., battery_mv=).
SCREENS = {
    "weather-glance": ("screens.weather_glance", "big now, next 12 h in 4 slots, today/tomorrow lines"),
    "weather-rain": ("screens.weather_rain", "rain headline + 24 h chance-of-rain chart"),
    "weather-haiku": ("screens.weather_haiku", "3/6 now block + 3/6 LLM weather haiku panel, 6 x 2-hourly slots"),
    "weather-proverb": ("screens.weather_proverb", "4/6 now block + 2/6 proverb of the day, 6 x 2-hourly slots"),
    "dashboard-glance": ("screens.dashboard_glance", "date, weather + month | 7-day agenda from macOS Calendar"),
    "weather-detailed": ("screens.weather", "dense: hourly x8, today/tomorrow cards, UV, sunset"),
    "auto": ("screens.auto", "weather-rain when heavy rain is coming (any rain before noon), else weather-proverb"),
}
ALIASES: dict[str, str] = {}


def load_config() -> dict:
    return tomllib.loads(CONFIG.read_text())


def set_screen(name: str):
    """Rewrite only the `screen = ...` line so comments in config.toml survive."""
    text = CONFIG.read_text()
    CONFIG.write_text(re.sub(r'(?m)^screen\s*=.*$', f'screen = "{name}"', text, count=1))


def resolve(name: str | None, cfg: dict) -> str:
    name = ALIASES.get(name, name) or cfg["screen"]
    if name not in SCREENS:
        raise SystemExit(f"unknown screen {name!r}; choose from {', '.join(SCREENS)}")
    return name


BATTERY_LOG = Path(__file__).resolve().parent.parent / ".cache" / "battery.csv"


def log_battery(mv: int):
    """Append every reading (time, mV): previews reuse the last one, and the trend will tell
    roughly how many days are left once the rail starts to sag."""
    BATTERY_LOG.parent.mkdir(exist_ok=True)
    with BATTERY_LOG.open("a") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%dT%H:%M:%S},{mv}\n")


def last_battery() -> int | None:
    try:
        return int(BATTERY_LOG.read_text().strip().splitlines()[-1].split(",")[1])
    except (OSError, IndexError, ValueError):
        return None


def build(name: str, cfg: dict, battery_mv: int | None = None) -> Image.Image:
    mod = importlib.import_module(SCREENS[name][0])
    mv = battery_mv if battery_mv is not None else last_battery()
    return mod.render(mod.fetch(cfg["lat"], cfg["lon"]), battery_mv=mv)


PUSH_LOG = BATTERY_LOG.parent / "push.log"
RETRY_STAGES = {"scan", "connect"}  # nothing reached the panel yet, so trying again is harmless
RETRY_WAIT = 10   # s; the tag advertises intermittently
WEAK_RSSI = -85   # dBm; below this, uploads start to drop


def log_push(name: str, outcome: str, e, attempt: int, secs: float, detail: str = ""):
    """One CSV row per attempt in .cache/push.log: time, layout, ok/fail, stage reached, RSSI (dBm),
    attempt, seconds, detail. RSSI over time shows whether failures track distance."""
    PUSH_LOG.parent.mkdir(exist_ok=True)
    with PUSH_LOG.open("a", newline="") as f:
        csv.writer(f).writerow([f"{dt.datetime.now():%Y-%m-%dT%H:%M:%S}", name, outcome, e.stage,
                                "" if e.rssi is None else e.rssi, attempt, round(secs), detail])


def explain(exc: BaseException, stage: str) -> str:
    """A one-line reason for the hq dashboard (its last log line)."""
    from bleak.exc import BleakBluetoothNotAvailableError
    from .device import DeviceNotFound
    if isinstance(exc, BleakBluetoothNotAvailableError):
        return f"Bluetooth unavailable on this Mac ({exc.args[0] if exc.args else exc}); under launchd, check bun's Bluetooth permission"
    if isinstance(exc, DeviceNotFound):
        return f"device not found ({exc}): out of range, between adverts, or another app is connected"
    if stage == "connect":
        return f"found the device but couldn't connect ({type(exc).__name__}: {exc}): weak signal or busy"
    return f"connection lost during {stage} ({type(exc).__name__}: {exc}): weak signal or the device reset"


def run_push(name: str, cfg: dict, wipe: bool) -> Image.Image | None:
    """push() with failure handling: log every attempt, retry once if it failed before anything
    reached the panel, and exit 1 with a readable reason so hq marks the run FAULT."""
    from bleak.exc import BleakBluetoothNotAvailableError
    from .device import EPD
    for attempt in (1, 2):
        e, t0 = EPD(), time.monotonic()
        try:
            img = asyncio.run(push(name, cfg, wipe, e))
            log_push(name, "ok", e, attempt, time.monotonic() - t0)
            return img
        except Exception as exc:
            reason = explain(exc, e.stage)
            log_push(name, "fail", e, attempt, time.monotonic() - t0, reason)
            if attempt == 1 and e.stage in RETRY_STAGES and not isinstance(exc, BleakBluetoothNotAvailableError):
                print(f"push attempt 1 failed: {reason}; retrying in {RETRY_WAIT} s")
                time.sleep(RETRY_WAIT)
                continue
            print(f"push failed: {reason}" + (f" (signal {e.rssi} dBm)" if e.rssi is not None else ""))
            sys.exit(1)


async def push(name: str, cfg: dict, wipe: bool, e) -> Image.Image | None:
    """Connect first so the frame can show the battery level the device just reported."""
    from .device import MODE_CALENDAR, WIPE_SECONDS
    async with e:
        mv = int(e.info["bat"]) if "bat" in e.info else None
        if mv:
            log_battery(mv)
        try:
            img = build(name, cfg, battery_mv=mv)
        except Exception as exc:
            # No fresh data: show the firmware's own date view rather than a stale forecast.
            print(f"render failed ({exc!r}); falling back to built-in calendar")
            await e.set_time(MODE_CALENDAR)
            await asyncio.sleep(2)
            return None
        drift = e.clock_drift()
        if drift is None or abs(drift) > 30:
            # SET_TIME forces a built-in redraw, so only resync when needed and let it finish.
            print(f"device clock off by {drift}s; resyncing")
            await e.set_time(MODE_CALENDAR)
            await asyncio.sleep(WIPE_SECONDS)
        black, red = to_planes(img, red=True, dither=False)  # red accents: wet hours, haze, battery LOW
        await e.show(black, red, wipe=wipe)
        await e.arm_fallback(MODE_CALENDAR)
        await asyncio.sleep(2)
    signal = f"signal {e.rssi} dBm" + (" weak" if e.rssi is not None and e.rssi < WEAK_RSSI else "")
    print(f"pushed {name} (battery {mv} mV, {signal}, clock drift {drift if drift is None else round(drift)}s), "
          "fallback armed for midnight")
    return img


def main():
    cfg = load_config()
    if len(sys.argv) > 1 and sys.argv[1] == "web":
        from . import web
        if "--background" in sys.argv:
            raise SystemExit(web.launch())
        idle = sys.argv[sys.argv.index("--idle") + 1] if "--idle" in sys.argv else None
        web.serve(open_page="--no-open" not in sys.argv, idle=int(idle) if idle else None)
        return
    if len(sys.argv) > 1 and sys.argv[1] in ("use", "show", "list"):
        if sys.argv[1] in ("use", "show"):
            if len(sys.argv) < 3:
                raise SystemExit(f"usage: {sys.argv[1]} <screen>")
            name = resolve(sys.argv[2], cfg)
            set_screen(name)
            print(f"default screen: {name}")
            if sys.argv[1] == "show":  # use + push in one go
                run_push(name, cfg | {"screen": name}, wipe=False)
        else:
            for name, (_, desc) in SCREENS.items():
                print(f"{'*' if name == cfg['screen'] else ' '} {name:11} {desc}")
        return

    ap = argparse.ArgumentParser()
    ap.add_argument("screen", nargs="?", help=f"one of {', '.join(SCREENS)} (default: config.toml)")
    ap.add_argument("--preview", metavar="PNG")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--wipe", action="store_true", help="full CLEAR first (slow; use ~once a day for ghosting)")
    ap.add_argument("--bat", type=int, help="battery mV to draw in previews")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    args = ap.parse_args()
    cfg |= {k: v for k, v in (("lat", args.lat), ("lon", args.lon)) if v is not None}
    name = resolve(args.screen, cfg)
    img = run_push(name, cfg, args.wipe) if args.push else build(name, cfg, battery_mv=args.bat)
    if args.preview and img:
        preview(img, red=True, dither=False).save(args.preview)
        print("wrote", args.preview)


if __name__ == "__main__":
    main()
