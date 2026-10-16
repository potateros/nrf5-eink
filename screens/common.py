"""Shared drawing helpers for the 1-bit 400x300 layouts (glance, rain)."""
import datetime as dt

from PIL import Image, ImageDraw, ImageFont

from epd import icons
from screens.weather import battery_level

HELVETICA = "/System/Library/Fonts/Helvetica.ttc"
MENLO = "/System/Library/Fonts/Menlo.ttc"
W, H = 400, 300


def bold(size: int) -> ImageFont.FreeTypeFont:
    """Helvetica Bold: headings and big numbers (stays solid without anti-aliasing)."""
    return ImageFont.truetype(HELVETICA, size, index=1)


def mono(size: int) -> ImageFont.FreeTypeFont:
    """Menlo: small body text (crisp without anti-aliasing, where Helvetica Regular breaks up)."""
    return ImageFont.truetype(MENLO, size, index=0)


def hour(t: dt.datetime) -> str:
    return f"{t:%-I%p}".lower()


def fit_bold(d: ImageDraw.ImageDraw, text: str, max_w: float, sizes=(20, 18, 16, 15)) -> ImageFont.FreeTypeFont:
    """Largest bold size from `sizes` that fits `text` in `max_w` pixels."""
    for size in sizes:
        if d.textlength(text, font=bold(size)) <= max_w:
            return bold(size)
    return bold(sizes[-1])


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
    """White canvas with the shared header: date left; place, time and (only if low) battery right."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.fontmode = "1"  # no anti-aliasing anywhere: pure black/white glyphs
    d.text((10, 6), fc.now.strftime("%a %-d %b"), font=bold(17), fill="black")
    right = f"{fc.place}  {hour(fc.now)[:-2]}:{fc.now:%M}{hour(fc.now)[-2:]}"
    if battery_mv and battery_level(battery_mv)[1] == "LOW":
        right = "BATT LOW  " + right
    d.text((W - 10, 8), right, font=mono(13), fill="black", anchor="ra")
    d.line((0, 30, W, 30), fill="black")
    return img, d
