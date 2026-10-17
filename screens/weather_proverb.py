"""Layout "proverb": the side-panel dashboard (screens/note.py) with a 2/6 panel showing the
proverb of the day from data/proverbs.json (one per calendar day, 02-29 included)."""
import datetime as dt
import json
from pathlib import Path

from PIL import Image

from screens import note, weather

PROVERBS = Path(__file__).resolve().parent.parent / "data" / "proverbs.json"
MAIN_COLS = 4  # main block = 4 of 6 hourly columns, proverb panel = 2


def for_day(day: dt.date) -> dict:
    """{'date': 'MM-DD', 'text': ..., 'by': ...} for that calendar day."""
    key = f"{day:%m-%d}"
    return next(p for p in json.loads(PROVERBS.read_text()) if p["date"] == key)


def fetch(lat: float, lon: float) -> dict:
    data = weather.fetch(lat, lon)
    data["proverb"] = for_day(dt.date.today())
    return data


def render(data: dict, now: dt.datetime | None = None, battery_mv: int | None = None) -> Image.Image:
    p = data.get("proverb") or for_day((now or dt.datetime.now()).date())
    return note.layout(data, p["text"], p["by"], MAIN_COLS, keep_breaks=False, now=now, battery_mv=battery_mv)
