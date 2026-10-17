"""WIP (2026-10-17): portrait 300x400 mockups (p1-p4); a push would rotate the frame 90 deg into 400x300.

Render: uv run python wip/portrait.py   (PNGs at 2x into wip/images/, plus portrait_sheet.png)
"""
import calendar as calmod
import datetime as dt
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import landscape as X  # shared data + helpers
from layouts import icons
from epd.image import preview
from layouts.dashboard_glance import HOLIDAYS, _fit, _when
from layouts.common import RED, battery_meter, bold, hour, icon_mid, medium, rain_bar, rain_ink, text_mid, text_top, wrap

PW, PH = 300, 400
OUT = X.OUT
fc, today, now, mv = X.fc, X.today, X.now, X.mv


def page():
    img = Image.new("RGB", (PW, PH), "white")
    d = ImageDraw.Draw(img); d.fontmode = "1"
    return img, d


def header(d, title=None):
    """Portrait header: date + place left, battery top-right, small stamp under it."""
    date = title or fc.now.strftime("%a %-d %b")
    d.text((10, 21), date, font=bold(21), fill="black", anchor="ls")
    battery_meter(d, PW - 10, 3, mv)
    stamp = f"{hour(now)[:-2]}:{now:%M}{hour(now)[-2:]}"
    d.text((PW - 10, 26), f"updated {stamp}", font=medium(12), fill="black", anchor="rs")
    d.line((0, 30, PW, 30), fill="black")


def save(img, name):
    p = preview(img, red=True, dither=False).convert("RGB")
    p.resize((PW * 2, PH * 2), Image.NEAREST).save(OUT / f"{name}.png")
    print("wrote", name)


def weather_strip(img, d, y):
    """icon | hi / lo | rain % on one line."""
    code = fc.daily["weather_code"][0]
    icon_mid(img, icons.wmo(code)[1], 24, y + 14, 28)
    hi, lo = round(fc.daily["temperature_2m_max"][0]), round(fc.daily["temperature_2m_min"][0])
    text_mid(d, 46, y + 14, f"{hi}° / {lo}°", bold(16))
    pct = fc.daily["precipitation_probability_max"][0]
    text_mid(d, PW - 10, y + 14, f"rain {pct}%", medium(14), align="r", fill=rain_ink(pct))
    return y + 32


def agenda(d, y, bottom, ndays, x0=10, x1=PW - 10, tw=56):
    days = X.agenda_days(ndays)
    for k in range(ndays):
        day = today + dt.timedelta(days=k)
        items = days.get(day, [])
        if k and not items:
            continue
        if y + 21 + 18 > bottom:
            break
        hink = RED if k == 0 else "black"
        text_top(d, x0, y, X.day_label(day) if k < 7 else day.strftime("%a %-d"), bold(16), fill=hink)
        text_top(d, x1, y + 4, day.strftime("%-d %b"), medium(12), align="r", fill=hink)
        y += 21
        d.line((x0, y - 3, x1, y - 3), fill=hink)
        if not items:
            text_top(d, x0, y + 3, "No events", medium(12)); y += 18
        room = int((bottom - y) // 18)
        shown = items if len(items) <= room else items[:max(0, room - 1)]
        for e in shown:
            text_top(d, x0, y + 3, _when(e), medium(12), fill=RED if e.get("reminder") else X.ink(e))
            tx = x0 + tw
            if e.get("reminder"):
                X.circle(d, tx - 12, y + 3)
            text_top(d, tx, y + 2, _fit(d, e["title"], medium(14), x1 - tx), medium(14), fill=X.ink(e))
            y += 18
        if len(shown) < len(items):
            text_top(d, x0 + tw, y + 3, f"+{len(items) - len(shown)} more", medium(12)); break
        y += 5
    return y


def month(d, y, x0=10, x1=PW - 10, holidays=frozenset()):
    text_top(d, x0, y, today.strftime("%B %Y"), bold(12))
    cw, rh = (x1 - x0) / 7, 15
    y += 18
    for c, name in enumerate("MTWTFSS"):
        text_top(d, x0 + c * cw + cw / 2, y, name, medium(12), align="m", fill=RED if c == 6 else "black")
    for r, week in enumerate(calmod.Calendar(0).monthdayscalendar(today.year, today.month)):
        cy = y + 21 + r * rh
        for c, day in enumerate(week):
            if not day:
                continue
            cx = x0 + c * cw + cw / 2
            if day == today.day:
                d.rectangle((cx - 10, cy - 7, cx + 9, cy + 6), fill=RED)
                text_mid(d, cx, cy, str(day), bold(12), align="m", fill="white")
            else:
                text_mid(d, cx, cy, str(day), medium(12), align="m", fill=RED if c == 6 or day in holidays else "black")
    return y + 21 + len(calmod.Calendar(0).monthdayscalendar(today.year, today.month)) * rh


# P1: portrait agenda: header, weather strip, 14-day agenda
def p_agenda():
    img, d = page(); header(d)
    y = weather_strip(img, d, 34)
    d.line((10, y, PW - 10, y), fill="black")
    agenda(d, y + 8, PH - 6, 14)
    save(img, "p1_portrait_agenda")


# P2: portrait at-a-glance: big date + weather, month, agenda
def p_glance():
    img, d = page()
    x = 10
    text_top(d, x, 10, today.strftime("%A"), bold(16))
    text_top(d, x, 32, str(today.day), bold(48))
    mx = x + d.textlength(str(today.day), font=bold(48)) + 7
    text_top(d, mx, 32, today.strftime("%b"), bold(21))
    text_top(d, mx, 57, today.strftime("%Y"), bold(16))
    # weather on the right of the date block
    code = fc.daily["weather_code"][0]
    icon_mid(img, icons.wmo(code)[1], 196, 30, 30)
    hi, lo = round(fc.daily["temperature_2m_max"][0]), round(fc.daily["temperature_2m_min"][0])
    text_mid(d, 216, 30, f"{hi}°/{lo}°", bold(16))
    text_top(d, 180, 52, _fit(d, icons.wmo(code)[0], medium(14), PW - 190), medium(14))
    pct = fc.daily["precipitation_probability_max"][0]
    text_top(d, 180, 69, f"rain {pct}%", medium(14), fill=rain_ink(pct))
    battery_meter(d, PW - 10, 3, mv)
    d.line((10, 90, PW - 10, 90), fill="black")
    hol = {dt.date.fromisoformat(e["start"][:10]).day for e in X.cal["events"]
           if e["calendar"] == HOLIDAYS and e["start"][:7] == f"{today:%Y-%m}"}
    y = month(d, 98, holidays=hol)
    d.line((10, y, PW - 10, y), fill="black")
    agenda(d, y + 8, PH - 6, 7)
    save(img, "p2_portrait_at_a_glance")


# P3: portrait reminders: Due, Tasks, Shopping stacked
def p_reminders():
    img, d = page(); header(d)
    by = X.rem_lists(); due = X.due_items()
    overdue = sum(r["start"].date() < today for r in due)
    y = X.rem_rows(d, 10, PW - 10, 38, PH - 6, due, "Due", head_ink=RED if overdue else "black",
                   right=f"{overdue} overdue" if overdue else str(len(due)), date=True)
    undated = lambda l: [{"title": r["title"]} for r in by[l] if not r.get("due")]
    y = X.rem_rows(d, 10, PW - 10, y, PH - 6, undated("Tasks"), "Tasks")
    X.rem_rows(d, 10, PW - 10, y, PH - 6, undated("Shopping"), "Shopping")
    save(img, "p3_portrait_reminders")


# P4: portrait weather: now block, 2-hourly rows (even hours), today/tomorrow
def p_weather():
    img, d = page(); header(d)
    icon_mid(img, icons.wmo(fc.cur["weather_code"])[1], 44, 72, 56, night=fc.night(now))
    temp = f"{round(fc.cur['temperature_2m'])}°"
    text_mid(d, 84, 66, temp, bold(48))
    tx = 84 + d.textlength(temp, font=bold(48)) + 10
    y = 44
    for line in wrap(d, fc.condition, bold(21), PW - 10 - tx, max_lines=2):
        text_top(d, tx, y, line, bold(21)); y += 22
    if fc.until:
        text_top(d, tx, y + 4, f"until {fc.until}", medium(14))
    if fc.psi > 50:
        text_top(d, 10, 108, f"Haze PSI {fc.psi}", medium(14), fill=RED if fc.psi > 100 else "black")
    d.line((0, 128, PW, 128), fill="black")
    # hourly rows
    y, rh = 136, 25
    for n in range(8):
        i = fc.even + 2 * n
        t = fc.times[i]
        cy = y + n * rh + rh / 2
        text_mid(d, 10, cy, hour(t), medium(14))
        icon_mid(img, icons.wmo(fc.hourly["weather_code"][i])[1], 82, cy, 22, night=fc.night(t))
        text_mid(d, 104, cy, f"{round(fc.hourly['temperature_2m'][i])}°", bold(16))
        rain_bar(d, 150, cy - 5, 90, 10, fc.rain(i))
        text_mid(d, PW - 10, cy, f"{fc.rain(i)}%", medium(14), align="r", fill=rain_ink(fc.rain(i)))
    y += 8 * rh + 4
    d.line((0, y, PW, y), fill="black")
    for k, label in enumerate(("Today", "Tmrw")):
        cy = y + 18 + k * 26
        text_mid(d, 10, cy, label, medium(16))
        icon_mid(img, icons.wmo(fc.daily["weather_code"][k])[1], 82, cy, 24)
        hi, lo = round(fc.daily["temperature_2m_max"][k]), round(fc.daily["temperature_2m_min"][k])
        text_mid(d, 104, cy, f"{hi}° / {lo}°", bold(16))
        pct = fc.daily["precipitation_probability_max"][k]
        text_mid(d, PW - 10, cy, f"rain {pct}%", medium(14), align="r", fill=rain_ink(pct))
    save(img, "p4_portrait_weather")


for f in (p_agenda, p_glance, p_reminders, p_weather):
    f()
ims = [Image.open(OUT / f"{n}.png") for n in ("p1_portrait_agenda", "p2_portrait_at_a_glance", "p3_portrait_reminders", "p4_portrait_weather")]
sheet = Image.new("RGB", (4 * 610, 800), (200, 200, 200))
for k, im in enumerate(ims):
    sheet.paste(im, (k * 610, 0))
sheet.save(OUT / "portrait_sheet.png")
