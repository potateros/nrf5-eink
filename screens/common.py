"""Shared drawing helpers for the 1-bit 400x300 layouts (glance, rain)."""
import datetime as dt
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from epd import icons
from screens.weather import battery_level

FONTS = Path(__file__).resolve().parent.parent / "fonts"
W, H = 400, 300
# Red is a signal colour, used only for what you might act on: wet hours (chance >= WET), unhealthy haze, BATT LOW.
# In a black/white push it thresholds to black (luminance 66 < INK_THRESHOLD), so layouts look unchanged.
RED = (220, 0, 0)
WET = 50  # % chance of rain that counts as "bring an umbrella" (same as rain_window)


def rain_ink(pct: int):
    return RED if pct >= WET else "black"


HAZE_PSI = 50  # show PSI unless it's in NEA's "Good" band (0-50); the owner watches haze closely


def haze_ink(psi: int):
    """Red from "Unhealthy" (> 100), when it's worth a mask; black while merely "Moderate"."""
    return RED if psi > 100 else "black"


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


@lru_cache(maxsize=None)
def regular(size: int) -> ImageFont.FreeTypeFont:
    """Lighter TRMNL weight for body text and labels. Snaps like bold(), except 14-15 px renders
    TRMNL16 Regular at 14, which stays clean off its native size (checked on the panel preview)."""
    if size >= 26:
        font = ImageFont.truetype(str(FONTS / "Inter.ttf"), size)
        font.set_variation_by_name("Regular")
        return font
    if size in (14, 15):
        font = ImageFont.truetype(str(FONTS / "TRMNL16-Regular.ttf"), 14)
        font.off_native = True
        return font
    native = 12 if size <= 13 else 16 if size <= 18 else 21
    return ImageFont.truetype(str(FONTS / f"TRMNL{native}-Regular.ttf"), native)


@lru_cache(maxsize=None)
def medium(size: int) -> ImageFont.FreeTypeFont:
    """Body text and labels: NicoClean (TRMNL's classic body pixel font, native 16 px). It's evenly
    weighted all round, between TRMNL Regular (too thin) and Bold (too heavy). Clean at 14-16 px;
    at <= 13 it gets cramped, so small labels use TRMNL12 Bold, which is equally even."""
    if size <= 13:
        return ImageFont.truetype(str(FONTS / "TRMNL12-Bold.ttf"), 12)
    font = ImageFont.truetype(str(FONTS / "NicoClean-Regular.ttf"), 16 if size >= 16 else size)
    font.off_native = size < 16
    return font


@lru_cache(maxsize=None)
def _dot(font) -> tuple[int, int]:
    """(left offset, width) of the ink in a "." glyph, measured by rendering it."""
    im = Image.new("1", (40, 40), 0)
    ImageDraw.Draw(im).text((10, 10), ".", font=font, fill=1)
    x0, _, x1, _ = im.getbbox()
    return x0 - 10, x1 - x0


def draw_text(d: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font, anchor: str = "la", fill="black"):
    """d.text, except that "…" is drawn as three tight periods in fonts used off their native pixel
    size (NicoClean/TRMNL16 at 14 px), where the real glyph smears into an underscore. The dots take
    the glyph's own advance, so measuring with "…" (e.g. in _fit) stays exact."""
    if "…" not in text or not getattr(font, "off_native", False):
        d.text(xy, text, font=font, fill=fill, anchor=anchor)
        return
    x = xy[0] - {"l": 0, "m": 0.5, "r": 1}[anchor[0]] * d.textlength(text, font=font)
    a = "l" + anchor[1]
    off, w = _dot(font)
    adv = font.getlength("…")
    step = max(w + 1, (adv - w) / 2.5)  # spread evenly inside the advance, at least 1 px apart
    for k, part in enumerate(text.split("…")):
        if k:
            for n in range(3):
                d.text((round(x + n * step) - off + 1, xy[1]), ".", font=font, fill=fill, anchor=a)
            x += adv
        d.text((x, xy[1]), part, font=font, fill=fill, anchor=a)
        x += d.textlength(part, font=font)


def _cap(font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    """(top, bottom) of a capital letter relative to the draw origin (anchor 'la')."""
    box = font.getbbox("H")
    return box[1], box[3]


def text_mid(d: ImageDraw.ImageDraw, x: float, cy: float, text: str, font, align: str = "l", fill="black"):
    """Draw text with its cap height centred on cy, so text and icons in a row share a centre line."""
    top, bottom = _cap(font)
    draw_text(d, (x, cy - (top + bottom) / 2), text, font, anchor=align + "a", fill=fill)


def text_top(d: ImageDraw.ImageDraw, x: float, top: float, text: str, font, align: str = "l", fill="black"):
    """Draw text so the top of its capitals sits exactly at `top`."""
    draw_text(d, (x, top - _cap(font)[0]), text, font, anchor=align + "a", fill=fill)


def icon_mid(img: Image.Image, kind: str, cx: float, cy: float, size: int, night: bool = False):
    """Draw a weather icon with its box centred on (cx, cy)."""
    icons.draw(img, kind, int(cx - size / 2), int(cy - size / 2), size, night=night)


def hour(t: dt.datetime) -> str:
    return f"{t:%-I%p}".lower()


def wrap_lines(d: ImageDraw.ImageDraw, text: str, font, max_w: float) -> list[tuple[str, bool]]:
    """Wrap keeping the text's own line breaks (e.g. a haiku). Returns (line, is_continuation)."""
    out = []
    for para in text.splitlines():
        for k, line in enumerate(wrap(d, para, font, max_w, max_lines=99)):
            out.append((line, k > 0))
    return out


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


def rain_sparkline(d: ImageDraw.ImageDraw, fc: "Forecast", k: int, x0: float, x1: float, cy: float, h: int = 18):
    """Day k's hourly chance of rain as 24 bars between x0 and x1, on a baseline centred at cy.
    Today's past hours are just dots on the baseline, so the bars show what's still ahead."""
    hours = fc.day_hours(k)[:24]
    bw, base = (x1 - x0) / 24, cy + h / 2
    this_hour = fc.now.replace(minute=0, second=0, microsecond=0)
    for n, i in enumerate(hours):
        x = x0 + n * bw
        if fc.times[i] < this_hour:
            d.point((x + 1, base), fill="black")
        else:
            d.rectangle((x, base - max(1, h * fc.rain(i) / 100), x + bw - 2, base), fill=rain_ink(fc.rain(i)))
    d.line((x0, base + 1, x1 - 2, base + 1), fill="black")


def day_row(img: Image.Image, d: ImageDraw.ImageDraw, fc: "Forecast", label: str, k: int, cy: float):
    """Today/Tmrw row: label | icon | high/low | 24 h rain sparkline | rain %."""
    text_mid(d, 10, cy, label, medium(16))
    icon_mid(img, icons.wmo(fc.daily["weather_code"][k])[1], 92, cy, 26)
    temps = f"{round(fc.daily['temperature_2m_max'][k])}° / {round(fc.daily['temperature_2m_min'][k])}°"
    text_mid(d, 118, cy, temps, bold(17))
    rain = f"rain {fc.daily['precipitation_probability_max'][k]}%"
    # red only while wet hours are still ahead (the daily max can be a shower that's already over)
    this_hour = fc.now.replace(minute=0, second=0, microsecond=0)
    ahead = max((fc.rain(i) for i in fc.day_hours(k) if fc.times[i] >= this_hour), default=0)
    text_mid(d, 390, cy, rain, medium(16), align="r", fill=rain_ink(ahead))
    x0 = 118 + d.textlength(temps, font=bold(17)) + 12
    x1 = 390 - d.textlength(rain, font=medium(16)) - 12
    rain_sparkline(d, fc, k, x0, x1, cy)


def rain_bar(d: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float, pct: int):
    d.rectangle((x, y, x + w, y + h), outline="black")
    if pct:
        d.rectangle((x, y, x + w * pct / 100, y + h), fill=rain_ink(pct))


class Forecast:
    """Convenience view over the data dict returned by screens.weather.fetch()."""

    def __init__(self, data: dict, now: dt.datetime):
        om = data["om"]
        self.now = now
        self.cur, self.hourly, self.daily = om["current"], om["hourly"], om["daily"]
        self.times = [dt.datetime.fromisoformat(t) for t in self.hourly["time"]]
        self.start = next(i for i, t in enumerate(self.times) if t > now)  # first future hour
        # first future even hour: 2-hourly slots read 10am, 12pm, 2pm... (owner, 2026-10-17)
        self.even = next(i for i in range(self.start, len(self.times)) if self.times[i].hour % 2 == 0)
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

    def day_hours(self, k: int) -> list[int]:
        """Hourly indices of day k (0 = today, 1 = tomorrow)."""
        day = self.now.date() + dt.timedelta(days=k)
        return [i for i, t in enumerate(self.times) if t.date() == day]

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


def battery_meter(d: ImageDraw.ImageDraw, x: float, top: float, mv: int | None, align: str = "r"):
    """Battery glyph modelled on the firmware calendar's (20x10 outline, 2x4 nub, inner bar) with
    the estimated %. align="r": right edge at `x`, label left of the glyph (the header corner);
    align="l": glyph starts at `x`, label to its right (the calendar layout's bottom-left corner).
    Red when it's time to charge."""
    small = medium(12)
    if mv is None:
        level, label, ink = 0.0, "?", "black"
    else:
        level, label = battery_level(mv)
        ink = RED if label.endswith("LOW") else "black"
    if align == "l":
        _battery_glyph(d, x, top, level, ink)
        draw_text(d, (x + 26, top + 9), label, small, anchor="ls", fill=ink)
        return
    x0 = x - 2 - 20
    _battery_glyph(d, x0, top, level, ink)
    draw_text(d, (x0 - 4, top + 9), label, small, anchor="rs", fill=ink)


def _battery_glyph(d: ImageDraw.ImageDraw, x0: float, top: float, level: float, ink):
    d.rectangle((x0, top, x0 + 19, top + 9), outline="black")
    d.rectangle((x0 + 20, top + 3, x0 + 21, top + 6), fill="black")
    if level:
        d.rectangle((x0 + 2, top + 2, x0 + 2 + max(1, round(15 * level)), top + 7), fill=ink)


def canvas(fc: Forecast, battery_mv: int | None) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """White canvas with the shared header: date + place on the left; on the right, the battery
    meter (always top-right, on every dashboard) above a small "updated 6:29pm" stamp. The stamp is
    deliberately tiny so it isn't mistaken for a live clock (the panel only changes on a push)."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.fontmode = "1"  # no anti-aliasing anywhere: pure black/white glyphs
    baseline, small = 21, medium(12)  # TRMNL12: the smallest font that stays readable on the panel
    date = fc.now.strftime("%a %-d %b")
    d.text((10, baseline), date, font=bold(21), fill="black", anchor="ls")
    draw_text(d, (10 + d.textlength(date, font=bold(21)) + 8, baseline), fc.place, small, anchor="ls")
    battery_meter(d, W - 10, 3, battery_mv)
    stamp = f"{hour(fc.now)[:-2]}:{fc.now:%M}{hour(fc.now)[-2:]}"
    draw_text(d, (W - 10, 26), f"updated {stamp}", small, anchor="rs")
    d.line((0, 30, W, 30), fill="black")
    return img, d
