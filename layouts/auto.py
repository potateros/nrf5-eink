"""Pseudo-layout "auto": picks the layout for the moment, so the 30-minute push follows the weather.

- `weather-rain` when a lot of rain is coming: the rain chart is what you want before heading out.
  Before noon (plans for the day are still open) any hour still ahead today with chance >= WET
  counts; from noon only the next RAIN_AHEAD hours count, and they need >= HEAVY.
  Rain falling now (NEA nowcast says showers/rain/thundery) always counts.
- `weather-proverb` otherwise.
"""
import datetime as dt

from PIL import Image

from layouts import weather_proverb as proverb, weather_rain as rain
from layouts.common import WET, Forecast

HEAVY = 70        # % chance that counts as "quite a lot" in the afternoon and evening
RAIN_AHEAD = 6    # hours looked ahead from noon on
NOON = 12
WET_WORDS = ("rain", "shower", "thunder", "drizzle")


def pick(fc: Forecast) -> tuple[str, str]:
    """(layout, reason)."""
    if any(w in fc.condition.lower() for w in WET_WORDS):
        return "weather-rain", f"raining now ({fc.condition})"
    if fc.now.hour < NOON:
        hours, threshold = [i for i in fc.day_hours(0) if i >= fc.start], WET
    else:
        hours, threshold = list(range(fc.start, fc.start + RAIN_AHEAD)), HEAVY
    wet = [i for i in hours if fc.rain(i) >= threshold]
    if wet:
        peak = max(wet, key=fc.rain)
        return "weather-rain", f"{fc.rain(peak)}% at {fc.times[peak]:%H:%M}"
    return "weather-proverb", "no heavy rain ahead"


def fetch(lat: float, lon: float) -> dict:
    return proverb.fetch(lat, lon)  # the weather data, plus whatever the proverb layout adds


def render(data: dict, now: dt.datetime | None = None, battery_mv: int | None = None) -> Image.Image:
    now = now or dt.datetime.now()
    name, why = pick(Forecast(data, now))
    print(f"auto: {name} ({why})")
    return (rain if name == "weather-rain" else proverb).render(data, now=now, battery_mv=battery_mv)
