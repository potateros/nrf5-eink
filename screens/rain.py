"""Layout B, "rain-first": headline answers when it rains, 24 h chance-of-rain chart, temps in the footer."""
import datetime as dt

from PIL import Image

from epd import icons
from screens.common import Forecast, bold, canvas, hour, mono
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

    d.text((10, 38), headline(fc), font=bold(30), fill="black")
    if fc.psi > 100:
        d.text((390, 46), f"PSI {fc.psi}", font=bold(16), fill="black", anchor="ra")
    d.text((10, 76), f"Now {round(fc.cur['temperature_2m'])}° · {fc.condition.lower()}", font=mono(16), fill="black")

    # 24 h chance-of-rain bars, dotted 50% line
    gx, gy, gw, gh = 30, 108, 360, 120
    d.line((gx, gy + gh, gx + gw, gy + gh), fill="black")
    for x in range(gx, gx + gw, 6):
        d.point((x, gy + gh / 2), fill="black")
    d.text((gx - 4, gy + gh / 2), "50", font=mono(12), fill="black", anchor="rm")
    bw = gw / 24
    for k in range(24):
        i = fc.start + k
        if i >= len(fc.times):
            break
        d.rectangle((gx + k * bw + 1, gy + gh - gh * fc.rain(i) / 100, gx + (k + 1) * bw - 2, gy + gh), fill="black")
        if k % 6 == 0:
            d.text((gx + k * bw, gy + gh + 4), hour(fc.times[i]), font=mono(13), fill="black")
    d.line((0, 254, 400, 254), fill="black")

    for n, (label, k) in enumerate((("Today", 0), ("Tmrw", 1))):
        x = 10 + n * 200
        icons.draw(img, icons.wmo(fc.daily["weather_code"][k])[1], x, 260, 32)
        d.text((x + 40, 262), label, font=mono(14), fill="black")
        hi, lo = round(fc.daily["temperature_2m_max"][k]), round(fc.daily["temperature_2m_min"][k])
        d.text((x + 40, 277), f"{hi}°/{lo}°", font=bold(18), fill="black")
    return img
