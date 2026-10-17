"""Owner-approved slot test (2026-10-17). Opcodes from the myetoys web tool (docs/DEVICE.md §2.0b):
0x31 [1, n] shows slot n (followed by SET_TIME mode 0), 0x33 [hi, lo] starts a carousel (minutes).
Never sends 0x32 (FREE_SLOT, irreversible). Webcam frames go to .cache/slot_test/.

  uv run python tools/experiments/slot_test.py state
  uv run python tools/experiments/slot_test.py show 0 7          # show slots 0 and 7, one after the other
  uv run python tools/experiments/slot_test.py slide 1 180       # 1-min carousel, watch 180 s
  uv run python tools/experiments/slot_test.py store 0 [raw]     # store a marker frame in slot 0 (RLE unless raw)

Hold the scheduler first (`hq hold eink-weather`) and restore with a normal push afterwards.
"""
import asyncio
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from epd.device import CHAR, EPD, MODE_PICTURE, REFRESH_SECONDS  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / ".cache" / "slot_test"
SET_SLOT, SET_SLIDE = 0x31, 0x33


def marker(slot: int):
    """Full-frame marker: text and a red bar near the bottom edge make truncation obvious."""
    from PIL import Image, ImageDraw
    from epd.image import to_planes
    from layouts.common import RED, bold
    img = Image.new("RGB", (400, 300), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 399, 299), outline="black", width=3)
    d.text((20, 20), f"SLOT {slot} - TOP", font=bold(26), fill="black")
    for y in range(60, 280, 20):
        d.text((20, y), f"row {y}", font=bold(16), fill="black" if y % 40 else RED)
    d.rectangle((200, 60, 380, 270), fill="black")
    d.rectangle((0, 280, 399, 299), fill=RED)
    d.text((140, 282), "BOTTOM", font=bold(16), fill="white")
    return to_planes(img, red=True, dither=False)


def snap(tag: str):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{time.strftime('%H%M%S')}_{tag}.jpg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "avfoundation", "-pixel_format", "uyvy422",
                    "-framerate", "30", "-video_size", "1920x1080", "-i", "HD Pro Webcam C920",
                    "-frames:v", "1", "-y", str(path)], check=False)
    print("  snap", path.name, flush=True)


async def state(e: EPD, label: str):
    seen = len(e.messages)
    # the firmware sends its config only when notifications are (re-)enabled, not on INIT
    await e.client.stop_notify(CHAR)
    await e.client.start_notify(CHAR, lambda _, b: e.messages.append(bytes(b)))
    await asyncio.sleep(0.5)
    await e._write(bytes([0x01]))
    await asyncio.sleep(1.5)
    new = e.messages[seen:]
    cfg = next((m for m in new if not m[:1].isalpha()), None)  # config is raw bytes, the rest is text
    text = [m.decode(errors="replace") for m in new if m is not cfg and not m.startswith(b"sid=")]
    print(f"{time.strftime('%H:%M:%S')} {label}: cfg={cfg.hex(' ') if cfg else None}"
          f" byte11={cfg[11] if cfg else '?'} byte13={cfg[13] if cfg and len(cfg) > 13 else '?'} {text}", flush=True)


async def main(cmd: str, args: list[str]):
    async with EPD() as e:
        await state(e, "baseline")
        if cmd == "show":
            for k in map(int, args):
                print(f"show slot {k}", flush=True)
                await e._write(bytes([SET_SLOT, 1, k]))
                await asyncio.sleep(1.0)
                await e.set_time(MODE_PICTURE)
                await asyncio.sleep(REFRESH_SECONDS)
                snap(f"slot{k}")
                await state(e, f"after show {k}")
        elif cmd == "store":
            k, raw = int(args[0]), "raw" in args
            black, red = marker(k)
            e.rle = e.rle and not raw
            print(f"store slot {k} ({'raw' if raw else 'rle' if e.rle else 'raw'})", flush=True)
            await e._write(bytes([SET_SLOT, 0, k]))
            await asyncio.sleep(1.0)
            await e.show(black, red)  # INIT, both planes, REFRESH, 30 s hold
            snap(f"stored{k}")
            await state(e, f"after store {k}")
        elif cmd == "slide":
            minutes, watch = int(args[0]), int(args[1]) if len(args) > 1 else 180
            await e._write(bytes([SET_SLIDE, minutes >> 8 & 0xFF, minutes & 0xFF]))
            await asyncio.sleep(2.0)
            await state(e, "after SET_SLIDE")
    if cmd == "slide":  # watch disconnected, as the carousel would run in normal use
        for i in range(watch // 20):
            await asyncio.sleep(20)
            snap(f"slide_{(i + 1) * 20:03d}s")
        async with EPD() as e:
            await state(e, "after watch")


asyncio.run(main(sys.argv[1], sys.argv[2:]))
