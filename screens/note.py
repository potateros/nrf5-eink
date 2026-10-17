"""Layout "note": glance with a compact main block, a side panel for an LLM weather haiku, and a
6-column hourly strip.

Grid: the hourly strip is 6 columns of 400/6 px. The main block spans `main_cols` of them and the
side panel the rest, so the panel divider always lines up with an hourly column divider (2.5/6 was
tried and breaks the grid). Hourly slots keep glance's slot proportions (100x112 -> 67x75).
`layout()` is shared with screens/proverb.py, which uses a 2/6 panel; the haiku uses 3/6.
"""
import datetime as dt

from PIL import Image

from epd import icons
from screens.common import (RED, Forecast, bold, canvas, day_row, hour, icon_mid, medium, rain_bar, text_mid,
                            text_top, wrap, wrap_lines)
from screens import quip, weather

COLS = 6
COL_W = 400 / COLS
MAIN_COLS = 3                                  # haiku layout: main block = 3 of 6 columns
MAIN_TOP, HOURLY_TOP, DAYS_TOP = 30, 163, 238  # horizontal rules
INDENT = 8  # continuation lines of a wrapped haiku line


def fetch(lat: float, lon: float) -> dict:
    """Weather data plus the LLM quip (cached; None when unavailable)."""
    data = weather.fetch(lat, lon)
    data["quip"] = quip.get(data, width=panel_text_width(MAIN_COLS))
    return data


def split_x(main_cols: float) -> int:
    """x of the main | panel divider."""
    return round(main_cols * COL_W)


def panel_text_width(main_cols: float) -> int:
    """Usable haiku line width in the side panel (continuation lines are indented)."""
    return 400 - split_x(main_cols) - 14 - INDENT


def note_text(data: dict) -> tuple[str, str | None]:
    """The LLM quip if there is one, else the fallback quote in config.toml [note]."""
    if data.get("quip"):
        return data["quip"], None
    from epd.cli import load_config  # lazy: cli imports layouts lazily too
    note = load_config().get("note", {})
    return note.get("text", ""), note.get("by")


def _main(img, d, fc: Forecast, split: int):
    cy = 70  # icon and temperature share this centre line
    icon_mid(img, icons.nea_kind(fc.condition), 38, cy, 56, night=fc.night(fc.now))
    text_mid(d, 74, cy, f"{round(fc.cur['temperature_2m'])}°", bold(56))

    # condition under them: one line at 21 px if it fits, else 16 px, wrapping to two lines if needed
    width = split - 20
    if d.textlength(fc.condition, font=bold(21)) <= width:
        lines, font, sub_y = [fc.condition], bold(21), 136
    else:
        font = bold(16)
        lines = wrap(d, fc.condition, font, width, max_lines=2)
        sub_y = 136 if len(lines) == 1 else 144
    for k, line in enumerate(lines):
        text_top(d, 10, (110 if len(lines) == 1 else 106) + k * 18, line, font)
    # (text, colour): the haze warning is red, like every "act on this" item
    parts = [p for p in ((fc.until and f"until {fc.until}", "black"), (fc.psi > 100 and f"Haze PSI {fc.psi}", RED))
             if p[0]]
    joined = " · ".join(t for t, _ in parts)
    if parts and d.textlength(joined, font=medium(14)) <= width:
        x = 10
        for k, (part, ink) in enumerate(parts):
            part = part if k == len(parts) - 1 else part + " · "
            text_top(d, x, sub_y, part, medium(14), fill=ink)
            x += d.textlength(part, font=medium(14))
    else:  # narrow main block: until / haze on their own lines
        for k, (part, ink) in enumerate(parts):
            text_top(d, 10, sub_y - 4 + k * 16, wrap(d, part, medium(14), width, max_lines=1)[0], medium(14), fill=ink)


def panel_lines(d, text: str, by: str | None, split: int, keep_breaks: bool):
    """Fit `text` (+ attribution) into the side panel. Returns (lines, font, line height, by_lines, fits)
    where lines are (text, is_continuation) pairs and `fits` is False if anything was cut."""
    width, by_lh, gap = 400 - split - 14, 13, 3
    by_lines = wrap(d, f"— {by}", medium(12), width, max_lines=2) if by else []
    avail = HOURLY_TOP - MAIN_TOP - 6 - (len(by_lines) * by_lh + gap if by_lines else 0)
    # auto-fit: NicoClean 14 px if it all fits, else the 12 px pixel font. With keep_breaks the text's
    # own line breaks are kept (haiku) and wrapped continuations are indented; prose wraps flush.
    for font, lh in ((medium(14), 16), (medium(12), 12)):
        room = int(avail // lh)
        if keep_breaks:
            lines = wrap_lines(d, text, font, width - INDENT)
        else:
            lines = [(line, False) for line in wrap(d, text, font, width, max_lines=99)]
        if len(lines) <= room:
            break
    full_by = not by or len(wrap(d, f"— {by}", medium(12), width, max_lines=99)) <= 2
    return lines[:room], font, lh, by_lines, len(lines) <= room and full_by


def _panel(d, text: str, by: str | None, split: int, keep_breaks: bool):
    if not text:
        return
    x0, by_lh, gap = split + 8, 13, 3
    lines, font, lh, by_lines, _ = panel_lines(d, text, by, split, keep_breaks)
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
        day_row(img, d, fc, label, k, 254 + row * 30)



def layout(data: dict, text: str, by: str | None, main_cols: float, keep_breaks: bool,
           now: dt.datetime | None = None, battery_mv: int | None = None) -> Image.Image:
    """The shared side-panel dashboard: main block | panel text, 6-column hourly, Today/Tmrw."""
    fc = Forecast(data, now or dt.datetime.now())
    img, d = canvas(fc, battery_mv)
    split = split_x(main_cols)
    _main(img, d, fc, split)
    d.line((split, MAIN_TOP + 6, split, HOURLY_TOP - 6), fill="black")
    _panel(d, text, by, split, keep_breaks)
    d.line((0, HOURLY_TOP, 400, HOURLY_TOP), fill="black")
    _hourly(img, d, fc)
    d.line((0, DAYS_TOP, 400, DAYS_TOP), fill="black")
    _days(img, d, fc)
    return img


def render(data: dict, now: dt.datetime | None = None, battery_mv: int | None = None) -> Image.Image:
    text, by = note_text(data)
    return layout(data, text, by, MAIN_COLS, keep_breaks=True, now=now, battery_mv=battery_mv)
