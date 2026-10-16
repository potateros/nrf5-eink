"""Layout A, "glance": big now block, next 12 h in 4 slots, today/tomorrow as one line each."""
import datetime as dt

from PIL import Image

from epd import icons
from screens.common import (Forecast, bold, canvas, fit_bold, hour, icon_mid, rain_bar, regular, text_mid,
                            text_top)
from screens.weather import fetch  # noqa: F401  (same data as the detailed screen)


def render(data: dict, now: dt.datetime | None = None, battery_mv: int | None = None) -> Image.Image:
    fc = Forecast(data, now or dt.datetime.now())
    img, d = canvas(fc, battery_mv)

    # now (y 31-126): icon centred on the block; temperature and condition share a cap-top line
    icon_mid(img, icons.nea_kind(fc.condition), 46, 78, 70, night=fc.night(fc.now))
    top = 46
    temp = f"{round(fc.cur['temperature_2m'])}°"
    text_top(d, 88, top, temp, bold(60))
    x2 = 96 + d.textlength(temp, font=bold(60))
    text_top(d, x2, top, fc.condition, fit_bold(d, fc.condition, 390 - x2))
    if fc.until:
        text_top(d, x2, top + 26, f"until {fc.until}", regular(15))
    if fc.psi > 100:
        text_top(d, x2, top + 48, f"Haze: PSI {fc.psi}", bold(14))
    d.line((0, 126, 400, 126), fill="black")

    # next 12 h (y 127-238): 4 columns, 3 h apart, every row on a shared centre line
    for n in range(4):
        i, cx = fc.start + 3 * n, 50 + n * 100
        t = fc.times[i]
        text_mid(d, cx, 142, hour(t), bold(14), align="m")
        icon_mid(img, icons.wmo(fc.hourly["weather_code"][i])[1], cx, 170, 34, night=fc.night(t))
        text_mid(d, cx, 201, f"{round(fc.hourly['temperature_2m'][i])}°", bold(18), align="m")
        rain_bar(d, cx - 30, 218, 60, 7, fc.rain(i))
        if n:
            d.line((n * 100, 132, n * 100, 230), fill="black")
    d.line((0, 238, 400, 238), fill="black")

    # today / tomorrow (y 239-300): label | icon | high/low | rain %, centred per row
    for row, (label, k) in enumerate((("Today", 0), ("Tmrw", 1))):
        cy = 254 + row * 30
        text_mid(d, 10, cy, label, bold(16))
        icon_mid(img, icons.wmo(fc.daily["weather_code"][k])[1], 92, cy, 26)
        hi, lo = round(fc.daily["temperature_2m_max"][k]), round(fc.daily["temperature_2m_min"][k])
        text_mid(d, 118, cy, f"{hi}° / {lo}°", bold(17))
        text_mid(d, 390, cy, f"rain {fc.daily['precipitation_probability_max'][k]}%", regular(15), align="r")
    return img
