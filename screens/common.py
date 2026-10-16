"""Shared drawing helpers for the 1-bit 400x300 layouts (glance, rain)."""
import datetime as dt
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from epd import icons
from screens.weather import battery_level

FONTS = Path(__file__).resolve().parent.parent / "fonts"
W, H = 400, 300


@lru_cache(maxsize=None)
def bold(size: int) -> ImageFont.FreeTypeFont:
    """The TRMNL type system for 1-bit screens (fonts/README.md).

    TRMNL12/16/21 are pixel fonts that only render cleanly at their native size, so the requested
    size snaps to the nearest one: <= 13 -> 12, 14-18 -> 16, 19-25 -> 21. From 26 px up it's Inter
    Bold, which holds up without anti-aliasing at large sizes."""
    if size >= 26:
        font = ImageFont.truetype(str(FONTS / "Inter.ttf"), size)
        font.set_variation_by_name("Bold")
        return font
    native = 12 if size <= 13 else 16 if size <= 18 else 21
    return ImageFont.truetype(str(FONTS / f"TRMNL{native}-Bold.ttf"), native)


def _cap(font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    """(top, bottom) of a capital letter relative to the draw origin (anchor 'la')."""
    box = font.getbbox("H")
    return box[1], box[3]


def text_mid(d: ImageDraw.ImageDraw, x: float, cy: float, text: str, font, align: str = "l"):
    """Draw text with its cap height centred on cy, so text and icons in a row share a centre line."""
    top, bottom = _cap(font)
    d.text((x, cy - (top + bottom) / 2), text, font=font, fill="black", anchor=align + "a")


def text_top(d: ImageDraw.ImageDraw, x: float, top: float, text: str, font, align: str = "l"):
    """Draw text so the top of its capitals sits exactly at `top`."""
    d.text((x, top - _cap(font)[0]), text, font=font, fill="black", anchor=align + "a")


def icon_mid(img: Image.Image, kind: str, cx: float, cy: float, size: int, night: bool = False):
    """Draw a weather icon with its box centred on (cx, cy)."""
    icons.draw(img, kind, int(cx - size / 2), int(cy - size / 2), size, night=night)


def hour(t: dt.datetime) -> str:
    return f"{t:%-I%p}".lower()


def fit_bold(d: ImageDraw.ImageDraw, text: str, max_w: float, sizes=(18, 17, 13)) -> ImageFont.FreeTypeFont:
    """Largest bold size from `sizes` that fits `text` in `max_w` pixels."""
    for size in sizes:
        if d.textlength(text, font=bold(size)) <= max_w:
            return bold(size)
    return bold(sizes[-1])


def wrap(d: ImageDraw.ImageDraw, text: str, font, max_w: float, max_lines: int = 2) -> list[str]:
    """Greedy word wrap into at most `max_lines`; the last line gets an ellipsis if text remains."""
    lines, cur = [], ""
    for word in text.split():
        candidate = f"{cur} {word}".strip()
        if cur and d.textlength(candidate, font=font) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = candidate
    lines.append(cur)
    if len(lines) > max_lines:
        last = " ".join(lines[max_lines - 1:])
        while d.textlength(last + "…", font=font) > max_w and " " in last:
            last = last.rsplit(" ", 1)[0]
        lines = lines[:max_lines - 1] + [last + "…"]
    return lines


def rain_bar(d: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float, pct: int):
    d.rectangle((x, y, x + w, y + h), outline="black")
    if pct:
        d.rectangle((x, y, x + w * pct / 100, y + h), fill="black")


class Forecast:
    """Convenience view over the data dict returned by screens.weather.fetch()."""

    def __init__(self, data: dict, now: dt.datetime):
        om = data["om"]
        self.now = now
        self.cur, self.hourly, self.daily = om["current"], om["hourly"], om["daily"]
        self.times = [dt.datetime.fromisoformat(t) for t in self.hourly["time"]]
        self.start = next(i for i, t in enumerate(self.times) if t > now)  # first future hour
        self._sun = list(zip((dt.datetime.fromisoformat(s) for s in self.daily["sunrise"]),
                             (dt.datetime.fromisoformat(s) for s in self.daily["sunset"])))
        self.place = data.get("nowcast", ("Singapore",))[0]
        if "nowcast" in data:  # NEA's area nowcast beats the model's current guess
            self.condition, period = data["nowcast"][1], data["nowcast"][2]
            # "Partly Cloudy (Day)" -> "Partly Cloudy": the sun/moon icon already says day or night
            self.condition = self.condition.replace(" (Day)", "").replace(" (Night)", "")
            self.until = period.split(" to ")[-1].replace(".00", "").replace(" ", "")  # "7.00 pm" -> "7pm"
        else:
            self.condition, self.until = icons.wmo(self.cur["weather_code"])[0], None
        self.psi = data.get("air", (0, 0))[0]

    def night(self, t: dt.datetime) -> bool:
        return not any(a <= t < b for a, b in self._sun)

    def rain(self, i: int) -> int:
        return self.hourly["precipitation_probability"][i] or 0

    def rain_window(self, i0: int, i1: int, threshold: int = 50) -> tuple[dt.datetime, dt.datetime] | None:
        """First run of hours with chance >= threshold in [i0, i1); returns (start, end-exclusive)."""
        run = None
        for i in range(i0, min(i1, len(self.times))):
            if self.rain(i) >= threshold:
                run = [self.times[i] if run is None else run[0], self.times[i]]
            elif run:
                break
        return (run[0], run[1] + dt.timedelta(hours=1)) if run else None


def canvas(fc: Forecast, battery_mv: int | None) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """White canvas with the shared header: date left; place, time and (only if low) battery right,
    both on one baseline."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.fontmode = "1"  # no anti-aliasing anywhere: pure black/white glyphs
    baseline = 21
    d.text((10, baseline), fc.now.strftime("%a %-d %b"), font=bold(21), fill="black", anchor="ls")
    right = f"{fc.place}  {hour(fc.now)[:-2]}:{fc.now:%M}{hour(fc.now)[-2:]}"
    if battery_mv and battery_level(battery_mv)[1] == "LOW":
        right = "BATT LOW  " + right
    d.text((W - 10, baseline), right, font=bold(16), fill="black", anchor="rs")
    d.line((0, 30, W, 30), fill="black")
    return img, d
