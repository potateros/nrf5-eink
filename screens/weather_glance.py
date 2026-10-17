"""Layout A, "weather-glance": big now block, next 12 h in 4 slots, today/tomorrow as one line each."""
import datetime as dt

from PIL import Image

from epd import icons
from screens.common import HAZE_PSI, RED, Forecast, bold, canvas, day_row, haze_ink, hour, icon_mid, medium, rain_bar, text_mid, text_top, wrap
from screens.weather import fetch  # noqa: F401  (same data as the detailed screen)


def render(data: dict, now: dt.datetime | None = None, battery_mv: int | None = None) -> Image.Image:
    fc = Forecast(data, now or dt.datetime.now())
    img, d = canvas(fc, battery_mv)

    # now (y 31-126): icon centred on the block, temperature centred on the icon, condition column
    # top-aligned
    icon_mid(img, icons.nea_kind(fc.condition), 46, 78, 70, night=fc.night(fc.now))
    top = 42
    temp = f"{round(fc.cur['temperature_2m'])}°"
    text_mid(d, 88, 78, temp, bold(60))
    x2 = 96 + d.textlength(temp, font=bold(60))
    # condition stays the most prominent text in the column: wrap at 21 px rather than shrink
    y = top
    for line in wrap(d, fc.condition, bold(21), 390 - x2):
        text_top(d, x2, y, line, bold(21))
        y += 22
    y += 4
    if fc.until:
        text_top(d, x2, y, f"until {fc.until}", medium(14))
        y += 17
    if fc.psi > HAZE_PSI:
        text_top(d, x2, y, f"Haze: PSI {fc.psi}", medium(14), fill=haze_ink(fc.psi))
    d.line((0, 126, 400, 126), fill="black")

    # next 12 h (y 127-238): 4 columns, 3 h apart, every row on a shared centre line
    for n in range(4):
        i, cx = fc.start + 3 * n, 50 + n * 100
        t = fc.times[i]
        text_mid(d, cx, 142, hour(t), medium(16), align="m")
        icon_mid(img, icons.wmo(fc.hourly["weather_code"][i])[1], cx, 170, 34, night=fc.night(t))
        text_mid(d, cx, 201, f"{round(fc.hourly['temperature_2m'][i])}°", bold(21), align="m")
        rain_bar(d, cx - 30, 218, 60, 7, fc.rain(i))
        if n:
            d.line((n * 100, 132, n * 100, 230), fill="black")
    d.line((0, 238, 400, 238), fill="black")

    # today / tomorrow (y 239-300): label | icon | high/low | rain sparkline | rain %
    for row, (label, k) in enumerate((("Today", 0), ("Tmrw", 1))):
        day_row(img, d, fc, label, k, 254 + row * 30)

    return img
