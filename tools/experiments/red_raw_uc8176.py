# FAILED EXPERIMENT (2026-10-16): screen ended up blank. Kept as a record; see docs/DEVICE.md §5.3.
# Run from the repo root: uv run python tools/experiments/red_raw_uc8176.py
"""Probe: black plane via normal upload, red plane via raw UC8176 commands (KWR mode, DTM1/DTM2)."""
import asyncio, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from PIL import Image, ImageDraw, ImageFont
from epd.device import EPD, MODE_CALENDAR, CMD_INIT, CMD_REFRESH, WIPE_SECONDS
from epd.image import _pack

W, H = 400, 300
f = lambda s: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", s, index=1)
blk = Image.new("1", (W, H), 0); d = ImageDraw.Draw(blk)       # 1 = ink
d.rectangle((0, 0, W - 1, H - 1), outline=1, width=2)
for x in range(0, W, 50): d.line((x, 0, x, 10 if x % 100 else 18), fill=1, width=2)   # ruler: tick every 50px
for y in range(0, H, 50): d.line((0, y, 10 if y % 100 else 18, y), fill=1, width=2)
d.text((30, 25), "RAW RED TEST  400x300", font=f(22), fill=1)
d.rectangle((30, 70, 160, 200), fill=1); d.text((40, 210), "BLACK", font=f(22), fill=1)
d.text((370, 270), "BR", font=f(18), fill=1)
red = Image.new("1", (W, H), 0); r = ImageDraw.Draw(red)        # 1 = red
r.rectangle((220, 70, 350, 200), fill=1); r.text((240, 210), "RED", font=f(22), fill=1)

black_plane = _pack(lambda x, y: not blk.getpixel((x, y)), W, H)  # 1 = white (EPD.show flips it)
red_plane = _pack(lambda x, y: red.getpixel((x, y)), W, H)         # raw: 1 = red

async def main():
    async with EPD() as e:
        cmd = lambda c, *data: e._write(bytes([0x03, c])) if not data else None
        async def raw(c, data=b""):
            await e._write(bytes([0x03, c]))
            for i in range(0, len(data), 242):
                await e._write(bytes([0x04]) + data[i:i + 242], response=(i // 242) % 8 == 7 or i + 242 >= len(data))
        await e.clear(); await asyncio.sleep(WIPE_SECONDS)             # wipe
        await e._write(bytes([CMD_INIT]))
        # UC8176 hypothesis: switch to KWR (B/W/R) mode, then DTM1 = black/white, DTM2 = red (upstream polarity)
        await raw(0x00, b"\x0F")               # PSR: KWR mode
        await raw(0x50, b"\x77")               # CDI: BWR setting from upstream
        await raw(0x10, black_plane)            # DTM1: 1 = white, 0 = black
        await raw(0x13, bytes(b ^ 0xFF for b in red_plane))  # DTM2: 0 = red
        await e._write(bytes([CMD_REFRESH]))
        await e.arm_fallback(MODE_CALENDAR)
        await asyncio.sleep(2)
asyncio.run(main())
