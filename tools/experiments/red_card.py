"""Push a black/white/red test card and time the refresh.

  uv run python tools/experiments/red_card.py [--wipe] [--hold 30] [--preview out.png]

The red plane uses the modern 0x30 flag (bit 0 = red), 0 = red, like upstream (SSD16xx inverts red RAM
via Display Update Control 1 = 0x80). After REFRESH it polls the app with a harmless notification
toggle (the firmware answers a CCCD enable by sending its config), which shows when the firmware is
free again, i.e. how long the refresh blocks it.
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image, ImageDraw  # noqa: E402

from epd import device  # noqa: E402
from epd.device import EPD  # noqa: E402
from epd.image import preview, to_planes  # noqa: E402
from screens.common import bold, medium  # noqa: E402

W, H = 400, 300
R, K = (220, 0, 0), (0, 0, 0)


def card() -> Image.Image:
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    d.rectangle((0, 0, W - 1, H - 1), outline=K, width=2)
    d.text((10, 8), "RED TEST", font=bold(26), fill=K)
    d.text((170, 8), "red", font=bold(26), fill=R)
    d.rectangle((10, 50, 130, 150), fill=R)
    d.text((14, 155), "solid red", font=medium(16), fill=K)
    d.rectangle((140, 50, 260, 150), fill=K)
    d.text((144, 155), "solid black", font=medium(16), fill=K)
    for i in range(0, 120, 8):  # alternating red/black stripes
        d.rectangle((270 + i, 50, 273 + i, 150), fill=R if i % 16 else K)
    d.text((274, 155), "stripes", font=medium(16), fill=K)
    d.text((10, 185), "Small red text 16px", font=medium(16), fill=R)
    d.text((10, 210), "Bold red 21px 12:34", font=bold(21), fill=R)
    d.line((10, 245, 390, 245), fill=R, width=1)
    d.line((10, 250, 390, 250), fill=K, width=1)
    d.text((10, 262), "1px red line / 1px black line", font=medium(16), fill=K)
    d.rectangle((W - 30, H - 30, W - 12, H - 12), fill=R)  # bottom-right corner marker
    return img


async def poll_ready(e: EPD, timeout: float) -> float | None:
    """Seconds until the firmware answers a notification re-enable with its config."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        seen = len(e.messages)
        await e.client.stop_notify(device.CHAR)
        await e.client.start_notify(device.CHAR, lambda _, b: e.messages.append(bytes(b)))
        for _ in range(10):
            await asyncio.sleep(0.1)
            if len(e.messages) > seen:
                return time.monotonic() - start
    return None


async def main(args):
    black, red = to_planes(card(), red=True, dither=False)
    async with EPD() as e:
        print("info:", e.info)
        if args.wipe:
            await e.clear()
            await asyncio.sleep(device.WIPE_SECONDS)
        await e.wait_ready()
        await e._write_plane(black, red=False)
        await e._write_plane(red, red=True)
        t0 = time.monotonic()
        await e._write(bytes([device.CMD_REFRESH]))
        busy = await poll_ready(e, timeout=args.hold + 60)
        print(f"firmware free again after {busy:.1f} s" if busy is not None else "no answer while polling")
        rest = args.hold - (time.monotonic() - t0)
        if rest > 0:
            await asyncio.sleep(rest)
        await e.arm_fallback()
    print("done")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--wipe", action="store_true")
    p.add_argument("--hold", type=float, default=device.REFRESH_SECONDS)
    p.add_argument("--preview")
    a = p.parse_args()
    if a.preview:
        preview(card(), red=True, dither=False).resize((W * 2, H * 2), Image.NEAREST).save(a.preview)
    else:
        asyncio.run(main(a))
