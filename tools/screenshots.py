"""Regenerate the README screenshots: docs/images/<layout>.png at 2x (pixel-exact).

  uv run python tools/screenshots.py

Weather is live. The calendar and reminders are NOT: the repo is public, so dashboard-glance is
drawn from the made-up agenda below, never from macOS Calendar or the reminders export.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PIL import Image  # noqa: E402

from eink.cli import SCREENS, build, last_battery, load_config  # noqa: E402
from epd.image import preview  # noqa: E402
from layouts import dashboard_glance  # noqa: E402
from sources import events, weather  # noqa: E402

OUT = ROOT / "docs" / "images"


def sample_agenda(today: dt.date) -> tuple[dict, list[dict], dict]:
    """(calendar export, reminders, [calendar] config) for a plausible, fictional week."""
    def at(days: int, hm: str) -> str:
        return f"{today + dt.timedelta(days=days)}T{hm}:00"

    def ev(title, cal, days, start, end, all_day=False):
        return {"title": title, "calendar": cal, "start": at(days, start), "end": at(days, end),
                "all_day": all_day, "my_status": "none"}

    cal = {"generated_at": None, "stale": False,
           "calendars": [{"title": "Home", "source": "iCloud"}, {"title": "Work", "source": "Work"},
                         {"title": dashboard_glance.HOLIDAYS, "source": "Holidays"}],
           "events": [
               ev("Dentist", "Home", 0, "10:30", "11:00"),
               ev("Dinner with Sam", "Home", 0, "19:00", "21:00"),
               ev("Team standup", "Work", 1, "09:30", "09:45"),
               ev("Design review", "Work", 1, "14:00", "15:00"),
               ev("Conference day", "Work", 2, "00:00", "23:59", all_day=True),
               ev("Yoga", "Home", 2, "18:30", "19:30"),
               ev("Sprint planning", "Work", 3, "10:00", "11:00"),
               ev("Parents visit", "Home", 5, "12:00", "15:00"),
           ]}
    rems = [{"title": t, "calendar": "Reminders", "start": dt.datetime.fromisoformat(at(d, "00:00")),
             "end": dt.datetime.fromisoformat(at(d, "00:00")), "all_day": True, "reminder": True}
            for t, d in (("Renew passport", -2), ("Water the plants", 0), ("Pay utilities bill", 1))]
    return cal, rems, {"exclude": [], "red_sources": ["Work"]}


def dashboard(cfg: dict) -> Image.Image:
    now = dt.datetime.now()
    cal, rems, conf = sample_agenda(now.date())
    data = weather.fetch(cfg["lat"], cfg["lon"]) | {"calendar": cal}
    real_reminders, real_config = events.reminders, dashboard_glance._config
    events.reminders, dashboard_glance._config = (lambda path: rems), (lambda: conf)
    try:
        return dashboard_glance.render(data, now=now, battery_mv=last_battery())
    finally:
        events.reminders, dashboard_glance._config = real_reminders, real_config


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    for name in SCREENS:
        if name == "auto":
            continue  # shows rain or proverb, which have their own screenshots
        img = dashboard(cfg) if name == "dashboard-glance" else build(name, cfg)
        img = preview(img, red=True, dither=False)  # exactly what the panel gets
        img.resize((img.width * 2, img.height * 2), Image.NEAREST).save(OUT / f"{name}.png", optimize=True)
        print("wrote", OUT / f"{name}.png")


if __name__ == "__main__":
    main()
