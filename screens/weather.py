"""Today + tomorrow weather screen for Singapore (Open-Meteo + NEA)."""
import datetime as dt
import math

from PIL import Image, ImageDraw, ImageFont

from epd import icons
from epd.data import fetch_json

NEA = "https://api-open.data.gov.sg/v2/real-time/api/"
FONT = "/System/Library/Fonts/Helvetica.ttc"
COMPASS = "N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split()


def psi_band(v: int) -> str:
    return ("Good", "Moderate", "Unhealthy", "Very unhealthy", "Hazardous")[
        (v > 50) + (v > 100) + (v > 200) + (v > 300)]


def battery_level(mv: int) -> tuple[float, str]:
    """(fill 0..1, label) from the firmware's `bat=` reading.

    The 1100 mAh Li-ion cell sits behind a ~3.0 V regulator and the firmware measures the
    regulated rail, so it reads ~2.92 V until the cell is nearly flat. A percentage would be
    fiction: report OK until the rail starts sagging, then LOW.
    """
    if mv >= 2850:
        return 1.0, "OK"
    return max(0.0, (mv - 2500) / 350), "LOW"


def draw_battery(d: ImageDraw.ImageDraw, right: int, cy: int, S, mv: int) -> int:
    """Draw a battery glyph + percentage ending at x=right, vertically centred; return its left x."""
    level, label = battery_level(mv)
    font = ImageFont.truetype(FONT, S(13), index=1)
    x1 = right - d.textlength(label, font=font) - S(4)
    d.text((right, cy), label, font=font, fill="black", anchor="rm")
    bw, bh = S(22), S(11)
    x0, y0 = x1 - bw - S(3), cy - bh // 2
    d.rectangle((x0, y0, x0 + bw, y0 + bh), outline="black", width=max(1, S(1.5)))
    d.rectangle((x0 + bw + 1, cy - S(3), x0 + bw + S(3), cy + S(3)), fill="black")
    fill = round((bw - S(4)) * level)
    if fill:
        d.rectangle((x0 + S(2), y0 + S(2), x0 + S(2) + fill, y0 + bh - S(2)), fill="black")
    return x0


def fetch(lat: float, lon: float) -> dict:
    om = fetch_json(
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&timezone=Asia/Singapore&forecast_days=3"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m"
        "&hourly=temperature_2m,precipitation_probability,weather_code"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
        "precipitation_sum,uv_index_max,sunrise,sunset,wind_speed_10m_max",
        ttl=900)
    out = {"om": om}
    # NEA extras are nice-to-have; screen still renders without them.
    try:
        two = fetch_json(NEA + "two-hr-forecast")["data"]
        meta = min(two["area_metadata"], key=lambda a: (a["label_location"]["latitude"] - lat) ** 2
                   + (a["label_location"]["longitude"] - lon) ** 2)
        item = two["items"][0]
        out["nowcast"] = (meta["name"], next(f["forecast"] for f in item["forecasts"] if f["area"] == meta["name"]),
                          item["valid_period"]["text"])
    except Exception:
        pass
    try:
        out["today_text"] = fetch_json(NEA + "twenty-four-hr-forecast")["data"]["records"][0]["general"]["forecast"]["text"]
        out["outlook"] = fetch_json(NEA + "four-day-outlook", ttl=3600)["data"]["records"][0]["forecasts"]
    except Exception:
        pass
    try:
        psi = fetch_json(NEA + "psi")["data"]
        r = psi["items"][0]["readings"]
        region = min(psi["regionMetadata"], key=lambda m: (m["labelLocation"]["latitude"] - lat) ** 2
                     + (m["labelLocation"]["longitude"] - lon) ** 2)["name"]
        out["air"] = (r["psi_twenty_four_hourly"][region],
                      fetch_json(NEA + "pm25")["data"]["items"][0]["readings"]["pm25_one_hourly"][region])
    except Exception:
        pass
    return out


def render(data: dict, w: int = 400, h: int = 300, now: dt.datetime | None = None,
           battery_mv: int | None = None) -> Image.Image:
    now = now or dt.datetime.now()
    k = min(w / 400, h / 300)
    S = lambda v: int(round(v * k))
    F = lambda size, bold=False: ImageFont.truetype(FONT, S(size), index=1 if bold else 0)
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)

    def fit(text, x, y, font, max_w, **kw):
        while text and d.textlength(text, font=font) > max_w:
            text = text[:-2] + "…"
        d.text((x, y), text, font=font, fill=kw.get("fill", "black"), anchor=kw.get("anchor", "la"))

    om = data["om"]
    cur, daily, hourly = om["current"], om["daily"], om["hourly"]
    sunrise = [dt.datetime.fromisoformat(s) for s in daily["sunrise"]]
    sunset = [dt.datetime.fromisoformat(s) for s in daily["sunset"]]
    is_night = lambda t: not any(a <= t < b for a, b in zip(sunrise, sunset))

    # header
    hb = S(24)
    d.line((0, hb, w, hb), fill="black", width=max(1, S(2)))
    d.text((S(8), hb // 2), now.strftime("%A %-d %B"), font=F(17, True), fill="black", anchor="lm")
    right = w - S(8)
    if battery_mv:
        right = draw_battery(d, right, hb // 2, S, battery_mv) - S(10)
    place = data.get("nowcast", ("Singapore",))[0]
    d.text((right, hb // 2), f"{place} · updated {now:%-I:%M%p}".replace("AM", "am").replace("PM", "pm"), font=F(13), fill="black", anchor="rm")

    # now
    y0 = hb + S(6)
    label, kind = icons.wmo(cur["weather_code"])
    sub = None
    if "nowcast" in data:  # NEA's observed-area nowcast beats the model's guess
        _, label, period = data["nowcast"]
        kind, sub = icons.nea_kind(label), "until " + period.split(" to ")[-1]
    icons.draw(img, kind, S(6), y0 + S(6), S(64), night=is_night(now) and kind in ("clear", "partly"))
    temp = f"{round(cur['temperature_2m'])}°"
    d.text((S(78), y0 + S(3)), temp, font=F(56, True), fill="black")
    digit_top = d.textbbox((S(78), y0 + S(3)), temp, font=F(56, True))[1]
    d.text((S(82), y0 + S(58)), f"Feels {round(cur['apparent_temperature'])}°", font=F(13), fill="black")
    x2, cw = S(196), w - S(196) - S(6)
    title = label + (f"  {sub}" if sub else "")
    title_y = digit_top - d.textbbox((0, 0), title, font=F(16, True))[1]  # glyph tops line up with the digits
    fit(title, x2, title_y, F(16, True), cw)
    wind_dir = COMPASS[int((cur["wind_direction_10m"] % 360) / 22.5 + 0.5) % 16]
    lines = [f"Humidity {cur['relative_humidity_2m']}%", f"Wind {wind_dir} {round(cur['wind_speed_10m'])} km/h"]
    if "air" in data:
        psi, pm = data["air"]
        lines.append(f"Air: PSI {psi} ({psi_band(psi).lower()})")
    for i, line in enumerate(lines):
        fit(line, x2, title_y + S(22 + i * 17), F(13), cw)

    # hourly strip: next 8 slots, 2h apart
    y1 = y0 + S(82)
    d.line((0, y1, w, y1), fill="black", width=max(1, S(2)))
    times = [dt.datetime.fromisoformat(t) for t in hourly["time"]]
    start = next(i for i, t in enumerate(times) if t > now)
    idx = [start + 2 * n for n in range(8) if start + 2 * n < len(times)]
    col = w / len(idx)
    for n, i in enumerate(idx):
        cx = col * n + col / 2
        t = times[i]
        hour = f"{t:%-I%p}".lower()
        if t.hour < 2 and t.date() != now.date():
            hour = f"{t:%a}"
        d.text((cx, y1 + S(10)), hour, font=F(12, True), fill="black", anchor="ma")
        icons.draw(img, icons.wmo(hourly["weather_code"][i])[1], int(cx - S(13)), y1 + S(24), S(26), night=is_night(t))
        d.text((cx, y1 + S(51)), f"{round(hourly['temperature_2m'][i])}°", font=F(14, True), fill="black", anchor="ma")
        p = hourly["precipitation_probability"][i] or 0
        bw, bh, by = col - S(14), S(5), y1 + S(69)
        d.rectangle((cx - bw / 2, by, cx + bw / 2, by + bh), outline="black", width=1)
        if p:
            d.rectangle((cx - bw / 2, by, cx - bw / 2 + bw * p / 100, by + bh), fill="black")
        d.text((cx, by + bh + S(2)), f"{p}%", font=F(11), fill="black", anchor="ma")
    for n in range(1, len(idx)):
        d.line((col * n, y1 + S(8), col * n, y1 + S(90)), fill="black", width=1)

    # today / tomorrow
    y2 = y1 + S(96)
    d.line((0, y2, w, y2), fill="black", width=max(1, S(2)))
    texts = [data.get("today_text"), (data.get("outlook") or [{}])[0].get("forecast", {}).get("summary")]
    half = w // 2
    for n, title in enumerate(("TODAY", "TMRW")):
        x = n * half + S(8)
        dl, kind = icons.wmo(daily["weather_code"][n])
        text = texts[n] or dl
        kind = icons.nea_kind(text) if texts[n] else kind
        d.text((x, y2 + S(5)), title, font=F(12, True), fill="black")
        icons.draw(img, kind, x, y2 + S(20), S(40))
        tx = x + S(48)
        hi = f"{round(daily['temperature_2m_max'][n])}°"
        d.text((tx, y2 + S(14)), hi, font=F(26, True), fill="black")
        d.text((tx + d.textlength(hi, font=F(26, True)) + S(4), y2 + S(25)), f"/ {round(daily['temperature_2m_min'][n])}°", font=F(14), fill="black")
        rain = f"Rain {daily['precipitation_probability_max'][n]}% · {daily['precipitation_sum'][n]:.0f} mm"
        fit(rain, tx, y2 + S(43), F(14, True), half - S(56))
        fit(text, x, y2 + S(64), F(13), half - S(16))
        fit(f"UV {daily['uv_index_max'][n]:.0f}  ·  Sunset {sunset[n]:%-I:%M}", x, y2 + S(80), F(12), half - S(16))
    d.line((half, y2 + S(6), half, h - S(4)), fill="black", width=1)
    return img
