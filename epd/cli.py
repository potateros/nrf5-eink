"""nrf5-eink CLI: render a screen to PNG and/or push it to the display.

  uv run python -m epd.cli --push                      # push the screen set in config.toml
  uv run python -m epd.cli rain --preview out.png      # render a specific screen
  uv run python -m epd.cli use rain                    # switch the default screen
  uv run python -m epd.cli list                        # available screens (* = current)
"""
import argparse
import asyncio
import importlib
import re
import sys
import tomllib
from pathlib import Path

from PIL import Image

from .image import preview, to_planes

CONFIG = Path(__file__).resolve().parent.parent / "config.toml"

# name -> (module, description). Each module has fetch(lat, lon) and render(data, ..., battery_mv=).
SCREENS = {
    "glance": ("screens.glance", "big now, next 12 h in 4 slots, today/tomorrow lines"),
    "rain": ("screens.rain", "rain headline + 24 h chance-of-rain chart"),
    "note": ("screens.note", "compact now block + quote/LLM side panel, 6 x 2-hourly slots"),
    "detailed": ("screens.weather", "dense: hourly x8, today/tomorrow cards, UV, sunset"),
}
ALIASES = {"weather": "detailed"}


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


def build(name: str, cfg: dict, battery_mv: int | None = None) -> Image.Image:
    mod = importlib.import_module(SCREENS[name][0])
    return mod.render(mod.fetch(cfg["lat"], cfg["lon"]), battery_mv=battery_mv)


async def push(name: str, cfg: dict, wipe: bool) -> Image.Image | None:
    """Connect first so the frame can show the battery level the device just reported."""
    from .device import EPD, MODE_CALENDAR, WIPE_SECONDS
    async with EPD() as e:
        mv = int(e.info["bat"]) if "bat" in e.info else None
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
        black, _ = to_planes(img, red=False, dither=False)
        await e.show(black, wipe=wipe)
        await e.arm_fallback(MODE_CALENDAR)
        await asyncio.sleep(2)
    print(f"pushed {name} (battery {mv} mV, clock drift {drift if drift is None else round(drift)}s), "
          "fallback armed for midnight")
    return img


def main():
    cfg = load_config()
    if len(sys.argv) > 1 and sys.argv[1] in ("use", "list"):
        if sys.argv[1] == "use":
            if len(sys.argv) < 3:
                raise SystemExit("usage: use <screen>")
            name = resolve(sys.argv[2], cfg)
            set_screen(name)
            print(f"default screen: {name}")
        else:
            for name, (_, desc) in SCREENS.items():
                print(f"{'*' if name == cfg['screen'] else ' '} {name:9} {desc}")
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
    img = asyncio.run(push(name, cfg, args.wipe)) if args.push else build(name, cfg, battery_mv=args.bat)
    if args.preview and img:
        preview(img, red=False, dither=False).save(args.preview)
        print("wrote", args.preview)


if __name__ == "__main__":
    main()
