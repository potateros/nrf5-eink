"""Layout "note": glance with a compact main block, a side panel for an LLM weather haiku, and a
6-column hourly strip.

Grid: the hourly strip is 6 columns of 400/6 px. The main block spans exactly 4 of them
(x 0-267) and the note panel the other 2, so the panel divider lines up with the 4th column
divider below. Hourly slots keep glance's slot proportions (100x112 -> 67x75).
"""
import datetime as dt

from PIL import Image

from epd import icons
from screens.common import (Forecast, bold, canvas, hour, icon_mid, medium, rain_bar, text_mid, text_top, wrap,
                            wrap_lines)
from screens import quip, weather

COLS = 6
COL_W = 400 / COLS
SPLIT = round(4 * COL_W)                       # 267: main | note
MAIN_TOP, HOURLY_TOP, DAYS_TOP = 30, 163, 238  # horizontal rules
INDENT = 8  # continuation lines of a wrapped haiku line


def fetch(lat: float, lon: float) -> dict:
    """Weather data plus the LLM quip (cached; None when unavailable)."""
    data = weather.fetch(lat, lon)
    data["quip"] = quip.get(data)
    return data


def note_text(data: dict) -> tuple[str, str | None]:
    """The LLM quip if there is one, else the fallback quote in config.toml [note]."""
    if data.get("quip"):
        return data["quip"], None
    from epd.cli import load_config  # lazy: cli imports layouts lazily too
    note = load_config().get("note", {})
    return note.get("text", ""), note.get("by")


def _main(img, d, fc: Forecast):
    cy = 70  # icon and temperature share this centre line
    icon_mid(img, icons.nea_kind(fc.condition), 38, cy, 56, night=fc.night(fc.now))
    text_mid(d, 74, cy, f"{round(fc.cur['temperature_2m'])}°", bold(56))

    # condition on one line under them: 21 px if it fits, else 16 px
    width = SPLIT - 20
    font = bold(21) if d.textlength(fc.condition, font=bold(21)) <= width else bold(16)
    text_top(d, 10, 110, wrap(d, fc.condition, font, width, max_lines=1)[0], font)
    sub = " · ".join(s for s in (fc.until and f"until {fc.until}", fc.psi > 100 and f"Haze PSI {fc.psi}") if s)
    if sub:
        text_top(d, 10, 136, wrap(d, sub, medium(14), width, max_lines=1)[0], medium(14))


def _note(d, data: dict):
    text, by = note_text(data)
    if not text:
        return
    x0, width, by_lh, gap = SPLIT + 8, 400 - SPLIT - 14, 13, 3
    by_lines = wrap(d, f"— {by}", medium(12), width, max_lines=2) if by else []
    avail = HOURLY_TOP - MAIN_TOP - 6 - (len(by_lines) * by_lh + gap if by_lines else 0)
    # auto-fit: NicoClean 14 px if it all fits, else the 12 px pixel font. The text's own line breaks
    # are kept (haiku); wrapped continuation lines are indented.
    for font, lh in ((medium(14), 16), (medium(12), 12)):
        room = int(avail // lh)
        lines = wrap_lines(d, text, font, width - INDENT)
        if len(lines) <= room:
            break
    lines = lines[:room]
    block = len(lines) * lh + (gap + len(by_lines) * by_lh if by_lines else 0)
    y = MAIN_TOP + (HOURLY_TOP - MAIN_TOP - block) / 2 + 2  # centred in the panel
    for line, continued in lines:
        text_top(d, x0 + (INDENT if continued else 0), y, line, font)
        y += lh
    y += gap
    for line in by_lines:
        text_top(d, x0, y, line, medium(12))
        y += by_lh


def _hourly(img, d, fc: Forecast):
    for n in range(COLS):
        i, cx = fc.start + 2 * n, COL_W * n + COL_W / 2
        t = fc.times[i]
        text_mid(d, cx, 175, hour(t), medium(14), align="m")
        icon_mid(img, icons.wmo(fc.hourly["weather_code"][i])[1], cx, 193, 22, night=fc.night(t))
        text_mid(d, cx, 217, f"{round(fc.hourly['temperature_2m'][i])}°", bold(16), align="m")
        rain_bar(d, cx - 22, 227, 44, 5, fc.rain(i))
        if n:
            d.line((round(COL_W * n), HOURLY_TOP + 4, round(COL_W * n), DAYS_TOP - 4), fill="black")


def _days(img, d, fc: Forecast):
    for row, (label, k) in enumerate((("Today", 0), ("Tmrw", 1))):
        cy = 254 + row * 30
        text_mid(d, 10, cy, label, medium(16))
        icon_mid(img, icons.wmo(fc.daily["weather_code"][k])[1], 92, cy, 26)
        hi, lo = round(fc.daily["temperature_2m_max"][k]), round(fc.daily["temperature_2m_min"][k])
        text_mid(d, 118, cy, f"{hi}° / {lo}°", bold(17))
        text_mid(d, 390, cy, f"rain {fc.daily['precipitation_probability_max'][k]}%", medium(16), align="r")


def render(data: dict, now: dt.datetime | None = None, battery_mv: int | None = None) -> Image.Image:
    fc = Forecast(data, now or dt.datetime.now())
    img, d = canvas(fc, battery_mv)
    _main(img, d, fc)
    d.line((SPLIT, MAIN_TOP + 6, SPLIT, HOURLY_TOP - 6), fill="black")
    _note(d, data)
    d.line((0, HOURLY_TOP, 400, HOURLY_TOP), fill="black")
    _hourly(img, d, fc)
    d.line((0, DAYS_TOP, 400, DAYS_TOP), fill="black")
    _days(img, d, fc)
    return img
