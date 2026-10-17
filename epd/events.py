"""Upcoming events from macOS Calendar, via the EventKit exporter in tools/calendar_export.swift.

Calendar access (TCC) belongs to the process macOS holds responsible. A bare CLI inherits the
terminal's or launchd's (bun's) grant, and neither has Calendars, nor can launchd show the prompt.
So the exporter is wrapped in a tiny app bundle (.cache/CalendarExport.app) and started with
`open`: it is then its own responsible process, with its own one-time grant ("nrf5-eink calendar
export" in System Settings > Privacy & Security > Calendars) that works the same under launchd.

Every good export is cached in .cache/events.json; when an export fails the last cache is used.

Reminders with a due date join the agenda the way Calendar.app shows them. They come from the
trml-byos Reminders export (refreshed every 5 min by the trml-reminders hq job), so this app needs no
Reminders grant of its own; the path is config.toml [calendar] reminders.
"""
import datetime as dt
import json
import subprocess
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, PLIST = ROOT / "tools" / "calendar_export.swift", ROOT / "tools" / "calendar_export.plist"
APP = ROOT / ".cache" / "CalendarExport.app"
EXE = APP / "Contents" / "MacOS" / "calendar-export"
CACHE = ROOT / ".cache" / "events.json"
SHOWN_STATUSES = {"none", "accepted"}  # "none" = not an invite (your own event)


def _build():
    """(Re)build the app bundle when the Swift source or its Info.plist is newer than the binary."""
    if EXE.exists() and EXE.stat().st_mtime >= max(SRC.stat().st_mtime, PLIST.stat().st_mtime):
        return
    info = APP / "Contents" / "Info.plist"
    EXE.parent.mkdir(parents=True, exist_ok=True)
    info.unlink(missing_ok=True)
    pb = "/usr/libexec/PlistBuddy"
    subprocess.run([pb, "-c", f"Merge {PLIST}", str(info)], check=True, capture_output=True)
    subprocess.run([pb, "-c", "Add :CFBundleExecutable string calendar-export",
                    "-c", "Add :CFBundlePackageType string APPL", "-c", "Add :LSUIElement bool true", str(info)],
                   check=True, capture_output=True)
    subprocess.run(["swiftc", "-O", "-o", str(EXE), str(SRC)], check=True, capture_output=True)
    # same ad-hoc identity every build, so the Calendar grant (keyed on the bundle id) survives
    subprocess.run(["codesign", "-s", "-", "-f", str(APP)], check=True, capture_output=True)


def _export(days: int) -> dict:
    _build()
    with tempfile.TemporaryDirectory() as tmp:
        out, err = Path(tmp) / "out.json", Path(tmp) / "err.txt"  # `open --stdout` appends, so use fresh files
        subprocess.run(["open", "-W", "-n", "--stdout", str(out), "--stderr", str(err), str(APP), "--args", str(days)],
                       check=True, timeout=150)
        if not out.exists() or not out.read_text().strip():
            raise RuntimeError(err.read_text().strip() if err.exists() else "calendar export wrote nothing")
        return json.loads(out.read_text())


def fetch(days: int = 7) -> dict:
    """{'generated_at', 'events': [...], 'calendars': [...], 'stale': bool}. Falls back to the cache."""
    try:
        data = _export(days)
        CACHE.write_text(json.dumps(data))
        return {**data, "stale": False}
    except Exception as e:  # no grant, swiftc missing, timeout: show the last good export
        print(f"calendar export failed ({e}); using cache")
        if CACHE.exists():
            return {**json.loads(CACHE.read_text()), "stale": True}
        return {"generated_at": None, "events": [], "calendars": [], "stale": True}


def by_day(events: list[dict], today: dt.date, days: int, now: dt.datetime,
           exclude: set[str] = frozenset()) -> dict[dt.date, list[dict]]:
    """Events grouped by local date for today .. today+days-1. All-day events appear on every day
    they cover; timed ones on their start day only. Invites are kept only once accepted: your own
    events ("none") and accepted ones show; pending, tentative and declined ones don't. Today's timed events that have already ended
    are dropped (it's an agenda: what's still ahead). Each day: all-day first, then by start time."""
    out: dict[dt.date, list[dict]] = {}
    last = today + dt.timedelta(days=days - 1)
    for e in events:
        if e["calendar"] in exclude or e.get("my_status", "none") not in SHOWN_STATUSES:
            continue
        start, end = dt.datetime.fromisoformat(e["start"]), dt.datetime.fromisoformat(e["end"])
        item = {**e, "start": start, "end": end}
        if e["all_day"]:
            day = max(start.date(), today)
            while day <= min(end.date(), last):
                out.setdefault(day, []).append(item)
                day += dt.timedelta(days=1)
        elif today <= start.date() <= last and not (start.date() == today and end <= now):
            out.setdefault(start.date(), []).append(item)
    for day, items in out.items():
        # proper duplicates only (same title and time, e.g. one meeting on two synced calendars);
        # similar titles like "World of Workato" / "WOW: World of Workato 2026" both stay
        seen, unique = set(), []
        for e in items:
            key = (e["title"].strip().casefold(), e["all_day"], e["start"], e["end"])
            if key not in seen:
                seen.add(key)
                unique.append(e)
        items[:] = unique
        items.sort(key=lambda e: (not e["all_day"], e["start"], e["title"]))
    return out


def reminders(path: str | None) -> list[dict]:
    """Incomplete reminders that have a due date, as agenda items ("reminder": True). Missing or
    unreadable export: none."""
    try:
        data = json.loads(Path(os.path.expanduser(path)).read_text()) if path else {}
    except (OSError, ValueError) as e:
        print(f"reminders unavailable ({e})")
        return []
    out = []
    for r in data.get("reminders", []):
        if not r.get("due"):
            continue
        start = dt.datetime.fromisoformat(f"{r['due']}T{r.get('time_label') or '00:00'}")
        out.append({"title": r["title"], "calendar": r.get("list", ""), "start": start, "end": start,
                    "all_day": not r.get("has_time"), "reminder": True})
    return out


def add_reminders(days: dict[dt.date, list[dict]], rems: list[dict], today: dt.date, horizon: int):
    """File reminders on their due day; overdue ones (still not done) on Today, where they need
    doing. Then re-sort each day: overdue first (oldest first), then all-day items, then by time."""
    last = today + dt.timedelta(days=horizon - 1)
    for r in rems:
        day = max(r["start"].date(), today)
        if day <= last:
            days.setdefault(day, []).append({**r, "overdue": r["start"].date() < today})
    for items in days.values():
        items.sort(key=lambda e: (0, e["start"], e["title"]) if e.get("overdue")
                   else (1, not e["all_day"], e["start"], e["title"]))
