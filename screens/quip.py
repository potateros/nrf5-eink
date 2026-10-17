"""LLM-written weather haiku for the "note" layout's side panel (OpenRouter, see epd/llm.py).

Cached in .cache/quip.json and regenerated only when the weather situation changes (condition,
until-time, rain window, haze band, or a new 3-hour block), so 30-minute pushes don't call the
model every time. Returns None on any failure so the layout can fall back to config.toml [note].
"""
import datetime as dt
import json
import re
import time
from pathlib import Path

from epd import llm
from PIL import Image, ImageDraw

from screens.common import Forecast, hour, medium, wrap_lines
from screens.weather import psi_band

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "quip.json"
MIN_WORDS, MAX_WORDS = 8, 22  # a 5-7-5 haiku in English
PANEL_W, PANEL_LINES = 400 - 200 - 14 - 8, 7  # default: note.py panel at 3/6, 14 px; note passes its width


def fits(text: str, width: int = PANEL_W) -> bool:
    """True if the haiku fits the side panel at the larger 14 px size."""
    d = ImageDraw.Draw(Image.new("1", (1, 1)))
    return len(wrap_lines(d, text, medium(14), width)) <= PANEL_LINES

SYSTEM = """You write a haiku for a small black-and-white e-ink weather display in a home in Punggol, \
Singapore.

Write ONE haiku (three lines, 5-7-5 syllables) about today's weather from the forecast you are given.
- Make it a quiet, specific image of the day, not a joke. Avoid puns and exclamation marks.
- Weave in the one practical thing that matters most today (an umbrella, a mask for the haze, \
shade or water for heat), shown through the image rather than as an instruction.
- Plain English, ordinary punctuation, no emoji, no title, no quotation marks, no explanation.
Reply with the three lines only, one per line."""


def facts(fc: Forecast, data: dict) -> str:
    """Plain-language forecast summary for the prompt."""
    lines = [f"Local time: {fc.now:%A %-d %B, %-I:%M %p}".replace("AM", "am").replace("PM", "pm"),
             f"Now: {round(fc.cur['temperature_2m'])}°C (feels like {round(fc.cur['apparent_temperature'])}°C), "
             f"{fc.condition}" + (f" until {fc.until}" if fc.until else "")]
    window = fc.rain_window(fc.start, fc.start + 12)
    lines.append(f"Rain likely {hour(window[0])} to {hour(window[1])}" if window else "Little rain expected next 12 hours")
    slots = ", ".join(f"{hour(fc.times[i])} {fc.rain(i)}%" for i in range(fc.start, min(fc.start + 12, len(fc.times)), 2))
    lines.append(f"Chance of rain by hour: {slots}")
    d = fc.daily
    lines.append(f"Today: high {round(d['temperature_2m_max'][0])}°C, low {round(d['temperature_2m_min'][0])}°C, "
                 f"rain chance {d['precipitation_probability_max'][0]}%, UV index {d['uv_index_max'][0]:.0f}"
                 + (f", NEA says: {data['today_text']}" if data.get("today_text") else ""))
    outlook = (data.get("outlook") or [{}])[0].get("forecast", {}).get("summary")
    lines.append(f"Tomorrow: high {round(d['temperature_2m_max'][1])}°C, rain chance {d['precipitation_probability_max'][1]}%"
                 + (f", NEA says: {outlook}" if outlook else ""))
    if fc.psi:
        lines.append(f"Haze: 24-hour PSI {fc.psi} ({psi_band(fc.psi).lower()})"
                     + ("; N95 masks advised outdoors" if fc.psi > 200 else ""))
    return "\n".join(lines)


def signature(fc: Forecast) -> str:
    window = fc.rain_window(fc.start, fc.start + 12)
    band = psi_band(fc.psi) if fc.psi else "none"
    return "|".join([f"{fc.now:%Y-%m-%d}", str(fc.now.hour // 3), fc.condition, str(fc.until),
                     str(window and (window[0].hour, window[1].hour)), band])


def clean(text: str) -> str:
    """Normalise to characters the pixel fonts have; drop wrapping quotes."""
    for a, b in {"‘": "'", "’": "'", "“": '"', "”": '"',
                 "–": "-", "—": " - ", " ": " "}.items():
        text = text.replace(a, b)
    lines = []
    for line in text.splitlines():  # keep the haiku's line breaks
        line = "".join(ch for ch in line if 32 <= ord(ch) < 127 or ch == "°")
        line = re.sub(r"\s+", " ", line).strip().strip('"').strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def generate(fc: Forecast, data: dict, attempts: int = 4, model: str | None = None,
             width: int = PANEL_W) -> tuple[str, str]:
    """Ask the model until a reply passes validation. Returns (haiku, model).

    openrouter/free picks a random free model per request, and some of them are useless here (a
    reasoning model that runs out of tokens, a content-safety classifier), so a bad reply just
    means "try again", which re-rolls the model."""
    base = facts(fc, data)
    prompt, problems = base, []
    for _ in range(attempts):
        try:
            text, used = llm.chat(SYSTEM, prompt, model=model)
        except Exception as exc:
            problems.append(str(exc))
            continue
        text = clean(text)
        words, lines = len(text.split()), len(text.splitlines())
        if lines == 3 and MIN_WORDS <= words <= MAX_WORDS and fits(text, width):
            return text, used
        problems.append(f"{used}: {lines} lines, {words} words")
        prompt = base + (f"\n\nA previous answer had {lines} lines and {words} words. "
                         "Reply with exactly three short lines (5-7-5 syllables).")
    raise RuntimeError("no usable haiku: " + "; ".join(problems))


def get(data: dict, now: dt.datetime | None = None, force: bool = False, width: int = PANEL_W) -> str | None:
    """Cached quip for the current forecast, or None if unavailable."""
    if not llm.configured():
        return None
    fc = Forecast(data, now or dt.datetime.now())
    sig = signature(fc)
    cached = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if not force and cached.get("sig") == sig:
        return cached["text"]
    try:
        text, model = generate(fc, data, width=width)
    except Exception as exc:
        print(f"quip: generation failed ({exc}); using fallback")
        return cached.get("text") if cached.get("sig", "").split("|")[0] == sig.split("|")[0] else None
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps({"sig": sig, "text": text, "model": model, "at": time.time()}))
    print(f"haiku ({model}): " + text.replace("\n", " / "))
    return text
