"""nrf5-eink CLI: render a screen to PNG and/or push it to the display.

  uv run python -m epd.cli weather --preview out.png
  uv run python -m epd.cli weather --push
"""
import argparse
import asyncio

from PIL import Image

from .image import preview, to_planes

LAT, LON = 1.4043, 103.9021  # Punggol; override with --lat/--lon
W, H = 400, 300


def build(name: str, args, battery_mv: int | None = None) -> Image.Image:
    if name == "weather":
        from screens import weather
        return weather.render(weather.fetch(args.lat, args.lon), W, H, battery_mv=battery_mv)
    raise SystemExit(f"unknown screen {name}")


async def push(args) -> Image.Image:
    """Connect first so the frame can show the battery level the device just reported."""
    from .device import EPD, MODE_CALENDAR, WIPE_SECONDS
    async with EPD() as e:
        mv = int(e.info["bat"]) if "bat" in e.info else None
        try:
            img = build(args.screen, args, battery_mv=mv)
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
        await e.show(black, wipe=not args.no_wipe)
        await e.arm_fallback(MODE_CALENDAR)
        await asyncio.sleep(2)
    print(f"pushed (battery {mv} mV, clock drift {drift if drift is None else round(drift)}s), fallback armed for midnight")
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("screen")
    ap.add_argument("--preview", metavar="PNG")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--no-wipe", action="store_true")
    ap.add_argument("--bat", type=int, help="battery mV to draw in previews")
    ap.add_argument("--lat", type=float, default=LAT)
    ap.add_argument("--lon", type=float, default=LON)
    args = ap.parse_args()
    img = asyncio.run(push(args)) if args.push else build(args.screen, args, battery_mv=args.bat)
    if args.preview and img:
        preview(img, red=False, dither=False).save(args.preview)
        print("wrote", args.preview)


if __name__ == "__main__":
    main()
