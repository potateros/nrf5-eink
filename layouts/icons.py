"""Weather glyphs drawn with PIL primitives, crisp at 1 bit."""
import math

from PIL import ImageDraw

# WMO weather code -> (label, icon kind)
WMO = {
    0: ("Clear", "clear"), 1: ("Mostly clear", "clear"), 2: ("Partly cloudy", "partly"),
    3: ("Overcast", "cloudy"), 45: ("Fog / haze", "fog"), 48: ("Fog", "fog"),
    51: ("Light drizzle", "drizzle"), 53: ("Drizzle", "drizzle"), 55: ("Heavy drizzle", "drizzle"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    80: ("Light showers", "rain"), 81: ("Showers", "rain"), 82: ("Heavy showers", "rain"),
    95: ("Thunderstorm", "thunder"), 96: ("Thunderstorm", "thunder"), 99: ("Thunderstorm", "thunder"),
}

# NEA forecast codes -> icon kind (falls back on keywords)
def nea_kind(text: str) -> str:
    t = text.lower()
    if "thunder" in t: return "thunder"
    if "shower" in t or "rain" in t: return "rain"
    if "drizzle" in t: return "drizzle"
    if "haz" in t or "mist" in t or "fog" in t: return "fog"
    if "partly" in t or "fair" in t and "cloud" in t: return "partly"
    if "cloud" in t or "overcast" in t: return "cloudy"
    return "clear"


def wmo(code: int) -> tuple[str, str]:
    return WMO.get(code, ("Unknown", "cloudy"))


def _sun(d, cx, cy, r, w):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline="black", width=w)
    for i in range(8):
        a = i * math.pi / 4
        d.line((cx + math.cos(a) * r * 1.45, cy + math.sin(a) * r * 1.45,
                cx + math.cos(a) * r * 1.9, cy + math.sin(a) * r * 1.9), fill="black", width=w)


def _moon(d, cx, cy, r, w):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="black")
    o = r * 0.55
    d.ellipse((cx - r + o, cy - r - o * 0.4, cx + r + o, cy + r - o * 0.4), fill="white")


def _cloud(d, x, y, s, w):
    """Outlined cloud in box (x, y, x+s, y+0.62s)."""
    parts = [(0.08, 0.30, 0.42, 0.62), (0.22, 0.05, 0.62, 0.55), (0.48, 0.18, 0.92, 0.62)]
    def blob(inset, fill):
        for a, b, c, e in parts:
            d.ellipse((x + a * s + inset, y + b * s + inset, x + c * s - inset, y + e * s - inset), fill=fill)
        d.rectangle((x + 0.25 * s + inset, y + 0.38 * s + inset, x + 0.75 * s - inset, y + 0.62 * s - inset), fill=fill)
    blob(0, "black")
    blob(w, "white")


def draw(img, kind: str, x: int, y: int, s: int, night: bool = False):
    """Draw icon `kind` in an s*s box at (x, y)."""
    d = ImageDraw.Draw(img)
    w = max(2, s // 16)
    if kind == "clear":
        (_moon if night else _sun)(d, x + s / 2, y + s / 2, s * (0.26 if not night else 0.32), w)
        return
    if kind == "partly":
        (_moon if night else _sun)(d, x + s * 0.62, y + s * 0.32, s * 0.17, w)
        _cloud(d, x, y + s * 0.28, s * 0.85, w)
        return
    cy = y + s * 0.08
    _cloud(d, x, cy, s, w)
    bottom = cy + 0.62 * s
    if kind == "rain" or kind == "drizzle":
        n, ln = (4, 0.22) if kind == "rain" else (3, 0.1)
        for i in range(n):
            px = x + s * (0.22 + i * 0.18)
            d.line((px, bottom + s * 0.06, px - s * 0.06, bottom + s * (0.06 + ln)), fill="black", width=w)
    elif kind == "thunder":
        b = [(0.55, 0.0), (0.36, 0.2), (0.5, 0.2), (0.38, 0.34), (0.66, 0.13), (0.52, 0.13), (0.62, 0.0)]
        d.polygon([(x + px * s, bottom - s * 0.06 + py * s) for px, py in b], fill="black")
    elif kind == "fog":
        for i in range(3):
            yy = bottom + s * (0.06 + i * 0.09)
            d.line((x + s * (0.1 + 0.08 * (i % 2)), yy, x + s * (0.9 - 0.08 * (i % 2)), yy), fill="black", width=w)
