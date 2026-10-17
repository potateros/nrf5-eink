"""WIP (2026-10-17): full-screen calendar (c1-c3) and reminders-only (r1-r2) mockups, landscape 400x300.

Not registered layouts yet. Render: uv run python wip/landscape.py   (PNGs at 2x into wip/images/)
"""
import calendar as calmod
import datetime as dt
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from epd import events
from epd.cli import last_battery, load_config
from epd.image import preview
from screens import weather
from screens.at_a_glance import HOLIDAYS, _fit, _when
from screens.common import H, RED, W, Forecast, bold, canvas, medium, text_mid, text_top, wrap

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "wip" / "images"
cfg = load_config(); conf = cfg.get("calendar", {})
now = dt.datetime.now(); today = now.date()
data = weather.fetch(cfg["lat"], cfg["lon"]); fc = Forecast(data, now)
cal = events.fetch(35)
red_cals = {c["title"] for c in cal["calendars"] if c["source"] in conf.get("red_sources", [])}
rems = events.reminders(conf.get("reminders"))
mv = last_battery()


def agenda_days(n):
    days = events.by_day(cal["events"], today, n, now, set(conf.get("exclude", [])))
    events.add_reminders(days, rems, today, n)
    return days


def ink(e):
    return RED if e["calendar"] == HOLIDAYS or e["calendar"] in red_cals else "black"


def circle(d, x, y):
    d.ellipse((x, y, x + 8, y + 8), outline="black")


def day_label(day):
    k = (day - today).days
    return "Today" if k == 0 else "Tomorrow" if k == 1 else day.strftime("%A")


def save(img, name):
    p = preview(img, red=True, dither=False).convert("RGB")
    p.resize((800, 600), Image.NEAREST).save(OUT / f"{name}.png")
    print("wrote", name)


# ---------- C1: week columns ----------
def week_columns():
    img, d = canvas(fc, mv)
    days = agenda_days(7)
    x0, cw, top = 4, (W - 8) / 7, 36
    for k in range(7):
        day = today + dt.timedelta(days=k)
        x = x0 + k * cw
        if k:
            d.line((x, top, x, H - 6), fill="black")
        hol = any(e["calendar"] == HOLIDAYS for e in days.get(day, []))
        hd_ink = RED if k == 0 or day.weekday() == 6 or hol else "black"
        text_top(d, x + cw / 2, top + 2, day.strftime("%a"), medium(12), align="m", fill=hd_ink)
        if k == 0:
            d.rectangle((x + 8, top + 16, x + cw - 8, top + 38), fill=RED)
            text_mid(d, x + cw / 2, top + 27, str(day.day), bold(21), align="m", fill="white")
        else:
            text_mid(d, x + cw / 2, top + 27, str(day.day), bold(21), align="m", fill=hd_ink)
        y = top + 46
        items = days.get(day, [])
        for i, e in enumerate(items):
            lines = [_fit(d, l, medium(12), cw - 8) for l in wrap(d, e["title"], medium(12), cw - 8, max_lines=2)]
            need = 13 + 13 * len(lines) + 5
            if y + need > H - 8 and i < len(items):
                text_top(d, x + 4, y, f"+{len(items) - i}", medium(12))
                break
            when = _when(e)
            text_top(d, x + 4, y, when, medium(12), fill=RED if e.get("reminder") else ink(e))
            if e.get("reminder"):
                circle(d, x + cw - 13, y)
            y += 13
            for line in lines:
                text_top(d, x + 4, y, line, medium(12), fill=ink(e))
                y += 13
            y += 5
    save(img, "c1_week_columns")


# ---------- C2: two-column 14-day agenda ----------
def two_col_agenda():
    img, d = canvas(fc, mv)
    days = agenda_days(14)
    cols = [(10, 194), (206, 390)]
    d.line((200, 36, 200, H - 8), fill="black")
    ci, y, top, bottom = 0, 36, 36, H - 6
    tw = 56
    for k in range(14):
        day = today + dt.timedelta(days=k)
        items = days.get(day, [])
        if k and not items:
            continue
        need = 21 + 16 * max(1, min(len(items), 2))
        if y + need > bottom:
            ci += 1; y = top
            if ci == len(cols):
                break
        x0, x1 = cols[ci]
        hink = RED if k == 0 else "black"
        text_top(d, x0, y, day_label(day) if k < 7 else day.strftime("%a %-d"), bold(16), fill=hink)
        text_top(d, x1, y + 4, day.strftime("%-d %b"), medium(12), align="r", fill=hink)
        y += 21
        d.line((x0, y - 3, x1, y - 3), fill=hink)
        if not items:
            text_top(d, x0, y + 3, "No events", medium(12)); y += 16
        for i, e in enumerate(items):
            if y + 16 > bottom:
                break
            text_top(d, x0, y + 3, "all day" if e["all_day"] and not e.get("reminder") else _when(e).replace("all day", ""),
                     medium(12), fill=RED if e.get("reminder") else ink(e))
            tx = x0 + tw
            if e.get("reminder"):
                circle(d, tx - 11, y + 3)
            text_top(d, tx, y + 2, _fit(d, e["title"], medium(14), x1 - tx), medium(14), fill=ink(e))
            y += 16
        y += 5
    save(img, "c2_two_column_agenda")


# ---------- C3: month grid with titles ----------
def month_grid():
    img, d = canvas(fc, mv)
    days = agenda_days(35)
    monday = today - dt.timedelta(days=today.weekday())
    weeks = [[monday + dt.timedelta(days=7 * r + c) for c in range(7)] for r in range(4)]  # rolling 4 weeks
    x0, cw, top = 4, (W - 8) / 7, 34
    for c, name in enumerate("MTWTFSS"):
        text_top(d, x0 + c * cw + cw / 2, top + 2, name, medium(12), align="m", fill=RED if c == 6 else "black")
    gy = top + 16
    rh = (H - 4 - gy) / len(weeks)
    for r, week in enumerate(weeks):
        y = gy + r * rh
        d.line((x0, y, W - 4, y), fill="black")
        for c, day in enumerate(week):
            x = x0 + c * cw
            if c:
                d.line((x, y, x, y + rh), fill="black")
            if day < today:
                text_mid(d, x + 3, y + 8, str(day.day), medium(12), fill="black")  # past: number only
                continue
            items = days.get(day, []) if day >= today else []
            hol = any(e["calendar"] == HOLIDAYS for e in items)
            num_ink = RED if c == 6 or hol else "black"
            if day == today:
                d.rectangle((x + 1, y + 1, x + 20, y + 14), fill=RED)
                text_mid(d, x + 3, y + 8, str(day.day), medium(12), fill="white")
            else:
                label = day.strftime("%-d %b") if day.day == 1 else str(day.day)  # mark the new month
                text_mid(d, x + 3, y + 8, label, medium(12), fill=num_ink)
            ty, room = y + 17, int((rh - 18) // 12)
            shown = items if len(items) <= room else items[:max(room - 1, 0)]
            for e in shown:
                if e.get("reminder"):
                    circle(d, x + 3, ty)
                    t = _fit(d, e["title"], medium(12), cw - 15)
                    text_top(d, x + 13, ty, t, medium(12), fill=ink(e))
                else:
                    text_top(d, x + 3, ty, _fit(d, e["title"], medium(12), cw - 6), medium(12), fill=ink(e))
                ty += 12
            if len(shown) < len(items):
                text_top(d, x + 3, ty, f"+{len(items) - len(shown)}", medium(12))
    d.line((x0, H - 4, W - 4, H - 4), fill="black")
    save(img, "c3_four_week_grid")


# ---------- reminders ----------
def rem_lists():
    data = json.loads(Path(os.path.expanduser(conf["reminders"])).read_text())
    by = defaultdict(list)
    for r in data["reminders"]:
        by[r["list"]].append(r)
    return by


def due_items():
    out = []
    for r in rems:
        out.append(r)
    out.sort(key=lambda r: r["start"])
    return out


def rem_rows(d, x0, x1, y, bottom, items, label, head_ink="black", right=None, date=False):
    text_top(d, x0, y, label, bold(16), fill=head_ink)
    text_top(d, x1, y + 4, right if right is not None else str(len(items)), medium(12), align="r", fill=head_ink)
    y += 21
    d.line((x0, y - 3, x1, y - 3), fill=head_ink)
    for i, r in enumerate(items):
        if y + 17 * 2 > bottom and i < len(items) - 1:
            text_top(d, x0 + 13, y + 3, f"+{len(items) - i} more", medium(12)); return y + 17
        circle(d, x0, y + 3)
        dw = 0
        if date:
            when = r["start"]
            od = when.date() < today
            lab = "today" if when.date() == today else f"{when:%-d %b}"
            if not r["all_day"]:
                lab += f" {when:%H:%M}"
            dw = d.textlength(lab, font=medium(12)) + 6
            text_top(d, x1, y + 3, lab, medium(12), align="r", fill=RED if od or when.date() == today else "black")
        text_top(d, x0 + 13, y + 2, _fit(d, r["title"], medium(14), x1 - x0 - 13 - dw), medium(14))
        y += 17
    return y + 6


def reminders_two_col():
    img, d = canvas(fc, mv)
    by = rem_lists()
    due = due_items()
    overdue = sum(r["start"].date() < today for r in due)
    d.line((200, 36, 200, H - 8), fill="black")
    y = rem_rows(d, 10, 192, 38, H - 6, due, "Due", head_ink=RED if overdue else "black",
                 right=f"{overdue} overdue" if overdue else str(len(due)), date=True)
    undated = lambda l: [{"title": r["title"]} for r in by[l] if not r.get("due")]
    rem_rows(d, 10, 192, y, H - 6, undated("Tasks"), "Tasks")
    y = rem_rows(d, 208, 390, 38, H - 6, undated("Shopping"), "Shopping")
    save(img, "r1_due_tasks_shopping")


def reminders_three_col():
    img, d = canvas(fc, mv)
    by = rem_lists()
    due = due_items()
    overdue = [r for r in due if r["start"].date() < today]
    # strip: overdue count + oldest titles
    y = 36
    text_top(d, 10, y + 2, f"{len(overdue)} overdue", bold(16), fill=RED if overdue else "black")
    names = ", ".join(r["title"] for r in overdue)
    x = 10 + d.textlength(f"{len(overdue)} overdue", font=bold(16)) + 8
    text_top(d, x, y + 4, _fit(d, names, medium(12), W - 10 - x), medium(12))
    d.line((0, y + 22, W, y + 22), fill="black")
    cols = [("Tasks", 10, 126), ("Inbox", 140, 256), ("Shopping", 270, 390)]
    for k, (name, x0, x1) in enumerate(cols):
        if k:
            d.line((x0 - 7, y + 26, x0 - 7, H - 8), fill="black")
        items = [r for r in by[name] if not r.get("due")]
        yy = y + 28
        text_top(d, x0, yy, name, bold(12))
        text_top(d, x1, yy, str(len(items)), medium(12), align="r")
        yy += 16
        for i, r in enumerate(items):
            lines = wrap(d, r["title"], medium(12), x1 - x0 - 11, max_lines=2)
            if yy + 13 * len(lines) > H - 20 and i < len(items):
                text_top(d, x0 + 11, yy, f"+{len(items) - i} more", medium(12)); break
            circle(d, x0, yy)
            for line in lines:
                text_top(d, x0 + 11, yy, line, medium(12)); yy += 13
            yy += 4
    save(img, "r2_three_lists")


if __name__ == "__main__":
    for f in (week_columns, two_col_agenda, month_grid, reminders_two_col, reminders_three_col):
        f()
