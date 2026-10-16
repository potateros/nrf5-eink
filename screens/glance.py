"""Layout A, "glance": big now block, next 12 h in 4 slots, today/tomorrow as one line each."""
import datetime as dt

from PIL import Image

from epd import icons
from screens.common import Forecast, bold, canvas, fit_bold, hour, mono, rain_bar
from screens.weather import fetch  # noqa: F401  (same data as the detailed screen)


def render(data: dict, now: dt.datetime | None = None, battery_mv: int | None = None) -> Image.Image:
    fc = Forecast(data, now or dt.datetime.now())
    img, d = canvas(fc, battery_mv)

    # now: icon | big temperature | condition, until-time, haze (only when PSI > 100)
    icons.draw(img, icons.nea_kind(fc.condition), 10, 40, 76, night=fc.night(fc.now))
    cond_font = fit_bold(d, fc.condition, 164)
    cond_top = d.textbbox((228, 44), fc.condition, font=cond_font)[1]
    temp = f"{round(fc.cur['temperature_2m'])}°"
    temp_y = cond_top - d.textbbox((0, 0), temp, font=bold(72))[1]  # digit tops line up with the condition
    d.text((96, temp_y), temp, font=bold(72), fill="black")
    d.text((228, 44), fc.condition, font=cond_font, fill="black")
    if fc.until:
        d.text((228, 70), f"until {fc.until}", font=mono(16), fill="black")
    if fc.psi > 100:
        d.text((228, 94), f"Haze: PSI {fc.psi}", font=bold(16), fill="black")
    d.line((0, 126, 400, 126), fill="black")

    # next 12 h: 4 slots, 3 h apart
    for n in range(4):
        i, cx = fc.start + 3 * n, 50 + n * 100
        t = fc.times[i]
        d.text((cx, 134), hour(t), font=bold(16), fill="black", anchor="ma")
        icons.draw(img, icons.wmo(fc.hourly["weather_code"][i])[1], cx - 18, 156, 36, night=fc.night(t))
        d.text((cx, 196), f"{round(fc.hourly['temperature_2m'][i])}°", font=bold(20), fill="black", anchor="ma")
        rain_bar(d, cx - 30, 222, 60, 7, fc.rain(i))
        if n:
            d.line((n * 100, 136, n * 100, 228), fill="black")
    d.line((0, 238, 400, 238), fill="black")

    # today / tomorrow
    for row, (label, k) in enumerate((("Today", 0), ("Tmrw", 1))):
        y = 244 + row * 28
        d.text((10, y + 2), label, font=bold(18), fill="black")
        icons.draw(img, icons.wmo(fc.daily["weather_code"][k])[1], 74, y - 2, 28)
        hi, lo = round(fc.daily["temperature_2m_max"][k]), round(fc.daily["temperature_2m_min"][k])
        d.text((112, y + 1), f"{hi}°/{lo}°", font=bold(20), fill="black")
        d.text((390, y + 3), f"rain {fc.daily['precipitation_probability_max'][k]}%", font=mono(17), fill="black", anchor="ra")
    return img
