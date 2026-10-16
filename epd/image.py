"""Convert PIL images into EPD bit planes."""
from PIL import Image

WHITE, BLACK, RED = (255, 255, 255), (0, 0, 0), (220, 0, 0)


def _pack(bits, w: int, h: int) -> bytes:
    bw = (w + 7) // 8
    out = bytearray(bw * h)
    for y in range(h):
        for x in range(w):
            if bits(x, y):
                out[y * bw + x // 8] |= 0x80 >> (x % 8)
    return bytes(out)


# Luminance below this counts as black when not dithering. Above 128 thickens anti-aliased
# strokes slightly, so small text doesn't break up on the panel.
INK_THRESHOLD = 170


def to_planes(img: Image.Image, red: bool = True, dither: bool = True,
              threshold: int = INK_THRESHOLD) -> tuple[bytes, bytes | None]:
    """Quantise to the panel palette and return (black_plane, red_plane)."""
    if not red and not dither:
        lum = img.convert("L").load()
        w, h = img.size
        return _pack(lambda x, y: lum[x, y] >= threshold, w, h), None  # 1 = white
    palette = [WHITE, BLACK] + ([RED] if red else [])
    pal = Image.new("P", (1, 1))
    pal.putpalette(sum(palette, ()) + (0, 0, 0) * (256 - len(palette)))
    q = img.convert("RGB").quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE)
    px, (w, h) = q.load(), q.size
    black = _pack(lambda x, y: px[x, y] != 1, w, h)  # 1 = not black
    redp = _pack(lambda x, y: px[x, y] != 2, w, h) if red else None  # 1 = not red
    return black, redp


def preview(img: Image.Image, red: bool = True, dither: bool = True, threshold: int = INK_THRESHOLD) -> Image.Image:
    black, redp = to_planes(img, red, dither, threshold)
    w, h = img.size
    bw = (w + 7) // 8
    out = Image.new("RGB", (w, h), WHITE)
    p = out.load()
    for y in range(h):
        for x in range(w):
            bit = 0x80 >> (x % 8)
            if redp and not redp[y * bw + x // 8] & bit:
                p[x, y] = RED
            elif not black[y * bw + x // 8] & bit:
                p[x, y] = BLACK
    return out
