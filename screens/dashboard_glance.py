"""Layout "dashboard-glance": a 140 px left column (today's date, today's weather, the month) and a 260 px
agenda of the coming days from macOS Calendar (epd/events.py).

The split started as the owner's 300 | 500 idea scaled to 400 px (150 | 250), then narrowed to 140
so agenda titles fit (130 crams the month grid). There's no shared header:
the left column carries the date, so the battery meter sits bottom-left (the corner with the most
room under a 5-6 row month) and the "updated" stamp bottom-right, in 24 h time like the agenda.
Red: today in the month grid, Sundays and public holidays, rain >= WET,
whole rows from the work calendar ([calendar] red_sources, matched on the calendar's account), and a
reminder's time (overdue ones show their due date instead, on Today).
Calendars to leave out are set in config.toml [calendar] exclude.
"""
import calendar
import datetime as dt

from PIL import Image, ImageDraw

from epd import events, icons
from screens import weather
from screens.common import (H, RED, W, Forecast, battery_meter, bold, draw_text, icon_mid, medium, rain_ink,
                            text_mid, text_top)

SPLIT = 140     # left column | agenda
DAYS = 7        # agenda horizon, today included
EXPORT_DAYS = 35  # exported further ahead so the month grid can mark this month's holidays
HOLIDAYS = "Holidays in Singapore"  # subscribed calendar: drawn red, like Sundays
TIME_W = 56     # agenda time column ("all day" / "19:30")
BULLET_W = 12   # reminder circle sits this far left of the title, in the time column's gutter


def _config() -> dict:
    from epd.cli import load_config  # lazy: cli imports layouts lazily too
    return load_config().get("calendar", {})


def fetch(lat: float, lon: float) -> dict:
    data = weather.fetch(lat, lon)
    data["calendar"] = events.fetch(EXPORT_DAYS)
    return data


def _left(img, d, fc: Forecast, today: dt.date, holidays: set[int], battery_mv: int | None):
    x = 10
    text_top(d, x, 10, today.strftime("%A"), bold(16))
    # big day number with month over year beside it, filling its cap height (32-68). Stacked
    # because "28" + "Oct 2026" on one line is wider than the column.
    text_top(d, x, 32, str(today.day), bold(48))
    mx = x + d.textlength(str(today.day), font=bold(48)) + 7
    text_top(d, mx, 32, today.strftime("%b"), bold(21))
    text_top(d, mx, 57, today.strftime("%Y"), bold(16))

    # today's weather: icon + high / low, condition, chance of rain
    code = fc.daily["weather_code"][0]
    icon_mid(img, icons.wmo(code)[1], x + 15, 92, 30)
    hi, lo = round(fc.daily["temperature_2m_max"][0]), round(fc.daily["temperature_2m_min"][0])
    text_mid(d, x + 38, 92, f"{hi}° / {lo}°", bold(16))
    text_top(d, x, 116, _fit(d, icons.wmo(code)[0], medium(14), SPLIT - 20), medium(14))
    pct = fc.daily["precipitation_probability_max"][0]
    text_top(d, x, 133, f"rain {pct}%", medium(14), fill=rain_ink(pct))

    d.line((x, 152, SPLIT - 10, 152), fill="black")

    # month: 7 columns filling the pane (18 px at 140), Monday first; Sundays and holidays red, today a red box
    text_top(d, x, 161, today.strftime("%B %Y"), bold(12))
    cw, top, rh, gx = (SPLIT - 14) // 7, 180, 15, x - 2
    for c, name in enumerate("MTWTFSS"):
        text_top(d, gx + c * cw + cw / 2, top, name, medium(12), align="m", fill=RED if c == 6 else "black")
    for r, week in enumerate(calendar.Calendar(0).monthdayscalendar(today.year, today.month)):
        cy = top + 21 + r * rh
        for c, day in enumerate(week):
            if not day:
                continue
            cx = gx + c * cw + cw / 2
            if day == today.day:
                d.rectangle((cx - 9, cy - 7, cx + 8, cy + 6), fill=RED)
                text_mid(d, cx, cy, str(day), bold(12), align="m", fill="white")
            else:
                ink = RED if c == 6 or day in holidays else "black"
                text_mid(d, cx, cy, str(day), medium(12), align="m", fill=ink)

    battery_meter(d, x, H - 14, battery_mv, align="l")


def _fit(d, text: str, font, width: float) -> str:
    """One line, cut by character (not word) so long titles use the full width, ending in "…"
    (common.draw_text keeps it crisp at off-native sizes)."""
    if d.textlength(text, font=font) <= width:
        return text
    while text and d.textlength(text.rstrip(" ,/-:") + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip(" ,/-:") + "…"


def _when(e: dict) -> str:
    if e.get("overdue"):
        return f"{e['start']:%-d %b}"
    if e["all_day"]:
        return "due" if e.get("reminder") else "all day"
    return f"{e['start']:%H:%M}"


def _agenda(d, days: dict[dt.date, list[dict]], today: dt.date, now: dt.datetime, stale: bool,
            red_cals: set[str]):
    x0, x1, bottom = SPLIT + 10, W - 10, H - 20
    head_h, row_h, gap = 21, 18, 5
    y = 10
    for k in range(DAYS):
        day = today + dt.timedelta(days=k)
        items = days.get(day, [])
        if k and not items:
            continue  # an agenda, not a schedule: skip empty days (but always show Today)
        if y + head_h + row_h > bottom:
            break
        label = "Today" if k == 0 else "Tomorrow" if k == 1 else day.strftime("%A")
        # day and date share one size and cap line, all black (owner, 2026-10-17)
        text_top(d, x0, y, label, bold(16))
        text_top(d, x1, y, day.strftime("%-d %b"), bold(16), align="r")
        y += head_h
        d.line((x0, y - 3, x1, y - 3), fill="black")
        if not items:
            text_top(d, x0, y + 3, "No events", medium(12))
            y += row_h
        room = int((bottom - y) // row_h)
        shown = items if len(items) <= room else items[:max(0, room - 1)]
        for e in shown:
            ev_ink = RED if e["calendar"] == HOLIDAYS or e["calendar"] in red_cals else "black"
            text_top(d, x0, y + 3, _when(e), medium(12), fill=RED if e.get("reminder") else ev_ink)
            tx = x0 + TIME_W
            if e.get("reminder"):
                # hollow circle, like Reminders' checkbox, in the gutter so titles stay aligned
                d.ellipse((tx - BULLET_W, y + 3, tx - BULLET_W + 8, y + 11), outline="black")
            text_top(d, tx, y + 2, _fit(d, e["title"], medium(14), x1 - tx), medium(14), fill=ev_ink)
            y += row_h
        if len(shown) < len(items):
            text_top(d, x0 + TIME_W, y + 3, f"+{len(items) - len(shown)} more", medium(12))
            y += row_h
            break
        y += gap
    stamp = f"updated {now:%H:%M}" + (" · calendar offline" if stale else "")
    draw_text(d, (x1, H - 5), stamp, medium(12), anchor="rs", fill=RED if stale else "black")


def render(data: dict, now: dt.datetime | None = None, battery_mv: int | None = None) -> Image.Image:
    now = now or dt.datetime.now()
    today = now.date()
    fc = Forecast(data, now)
    cal = data.get("calendar") or {"events": [], "stale": True}
    conf = _config()
    days = events.by_day(cal["events"], today, DAYS, now, set(conf.get("exclude", [])))
    events.add_reminders(days, events.reminders(conf.get("reminders")), today, DAYS)
    red_cals = {c["title"] for c in cal.get("calendars", []) if c["source"] in conf.get("red_sources", [])}
    holidays = {dt.date.fromisoformat(e["start"][:10]).day for e in cal["events"]
                if e["calendar"] == HOLIDAYS and e["start"][:7] == f"{today:%Y-%m}"}

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.fontmode = "1"  # no anti-aliasing anywhere
    _left(img, d, fc, today, holidays, battery_mv)
    d.line((SPLIT, 10, SPLIT, H - 10), fill="black")
    _agenda(d, days, today, now, cal.get("stale", False), red_cals)
    return img
