"""Probe (2026-10-16): is the controller SSD16xx-compatible? Black plane via the normal 0x30 upload, red
plane via raw SEND_CMD/SEND_DATA: 0x4E/0x4F (RAM counters to origin) + 0x26 (write red RAM). Then the
firmware's own REFRESH, held 30 s. A red box on the right half means the SSD16xx command set works.

Only RAM-address and RAM-write commands are sent. Never send OTP/LUT/voltage commands (0x2A, 0x30, 0x32,
0x36, 0x39, 0x03, 0x04, 0x2C) or UC81xx 0xA0/0xA1: some are one-time-programmable.

  uv run python tools/experiments/raw_ssd1619_probe.py
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image, ImageDraw  # noqa: E402

from epd import device  # noqa: E402
from epd.device import EPD  # noqa: E402
from epd.image import to_planes  # noqa: E402
from screens.common import bold  # noqa: E402

W, H = 400, 300
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
d.fontmode = "1"
d.rectangle((0, 0, W - 1, H - 1), outline="black", width=2)
d.text((12, 10), "RAW SSD1619 PROBE", font=bold(26), fill="black")
d.rectangle((20, 70, 180, 230), fill="black")
d.text((20, 245), "black: 0x30 upload", font=bold(16), fill="black")
d.text((210, 245), "red: raw 0x26", font=bold(16), fill="black")
black, _ = to_planes(img, red=False, dither=False)

redimg = Image.new("RGB", (W, H), "white")
ImageDraw.Draw(redimg).rectangle((220, 70, 380, 230), fill=(220, 0, 0))
_, red = to_planes(redimg, red=True, dither=False)  # 0 = red


async def main():
    async with EPD() as e:
        async def raw(c, data=b""):
            await e._write(bytes([0x03, c]))
            for i in range(0, len(data), 242):
                last = i + 242 >= len(data)
                await e._write(bytes([0x04]) + data[i:i + 242], response=last or (i // 242) % 8 == 7)
        await e.wait_ready()
        await e._write_plane(black, red=False)
        await raw(0x4E, b"\x00")
        await raw(0x4F, b"\x00\x00")
        await raw(0x26, red)
        print("REFRESH at", time.strftime("%H:%M:%S"), flush=True)
        await e._write(bytes([device.CMD_REFRESH]))
        await asyncio.sleep(device.REFRESH_SECONDS)
        await e.arm_fallback()


asyncio.run(main())
