"""Push a black/white test card (border, gradient, corner labels) to check polarity, orientation and size.

  uv run python tools/testcard.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import asyncio
from PIL import Image, ImageDraw, ImageFont
from epd.device import EPD
from epd.image import to_planes

W, H = 400, 300
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
f = lambda s: ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", s)
d.rectangle((0, 0, W - 1, H - 1), outline="black", width=2)
d.text((10, 8), "BW TEST - top left", font=f(24), fill="black")
d.rectangle((10, 45, 110, 145), fill="black")
d.text((120, 60), "Square = solid black", font=f(20), fill="black")
for x in range(W - 20):  # gradient bar, dithered
    g = int(255 * x / (W - 21)); d.line((10 + x, 160, 10 + x, 200), fill=(g, g, g))
d.text((10, 205), "dithered gradient: black -> white", font=f(16), fill="black")
d.text((10, 240), "1", font=f(50), fill="black")
d.text((300, 270), "bottom right", font=f(16), fill="black")
black, _ = to_planes(img, red=False, dither=True)

async def main():
    async with EPD() as e:
        await e.show(black, wipe=True)
        await asyncio.sleep(2)
asyncio.run(main())
