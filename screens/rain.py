"""Layout B, "rain-first": headline answers when it rains, 24 h chance-of-rain chart, temps in the footer."""
import datetime as dt

from PIL import Image

from epd import icons
from screens.common import Forecast, bold, canvas, hour, icon_mid, regular, text_mid, text_top
from screens.weather import fetch  # noqa: F401


def headline(fc: Forecast) -> str:
    window = fc.rain_window(fc.start, fc.start + 24)
    if not window:
        return "Dry next 24 hours"
    a, b = window
    when = "Rain tmrw" if a.date() != fc.now.date() else "Rain"
    if b.date() != a.date() and b.hour == 0:
        return f"{when} from {hour(a)}"
    return f"{when} {hour(a)}–{hour(b)}"


def render(data: dict, now: dt.datetime | None = None, battery_mv: int | None = None) -> Image.Image:
    fc = Forecast(data, now or dt.datetime.now())
    img, d = canvas(fc, battery_mv)

    text_top(d, 10, 42, headline(fc), bold(26))
    if fc.psi > 100:
        text_top(d, 390, 42, f"PSI {fc.psi}", regular(16), align="r")
    text_top(d, 10, 78, f"Now {round(fc.cur['temperature_2m'])}° · {fc.condition.lower()}", regular(16))

    # 24 h chance-of-rain bars, dotted 50% line
    gx, gy, gw, gh = 30, 108, 360, 120
    d.line((gx, gy + gh, gx + gw, gy + gh), fill="black")
    for x in range(gx, gx + gw, 6):
        d.point((x, gy + gh / 2), fill="black")
    text_mid(d, gx - 4, gy + gh / 2, "50", bold(11), align="r")
    bw = gw / 24
    for k in range(24):
        i = fc.start + k
        if i >= len(fc.times):
            break
        d.rectangle((gx + k * bw + 1, gy + gh - gh * fc.rain(i) / 100, gx + (k + 1) * bw - 2, gy + gh), fill="black")
        if k % 6 == 0:
            text_top(d, gx + k * bw, gy + gh + 6, hour(fc.times[i]), bold(12))
    d.line((0, 254, 400, 254), fill="black")

    for n, (label, k) in enumerate((("Today", 0), ("Tmrw", 1))):
        x, cy = 10 + n * 200, 277
        icon_mid(img, icons.wmo(fc.daily["weather_code"][k])[1], x + 16, cy, 32)
        hi, lo = round(fc.daily["temperature_2m_max"][k]), round(fc.daily["temperature_2m_min"][k])
        text_mid(d, x + 40, cy - 9, label, regular(12))
        text_mid(d, x + 40, cy + 8, f"{hi}° / {lo}°", bold(16))
    return img
