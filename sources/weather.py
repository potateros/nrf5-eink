"""Weather for Singapore: Open-Meteo forecast + NEA nowcast, outlook and haze (data.gov.sg), cached."""
from sources.cache import fetch_json

NEA = "https://api-open.data.gov.sg/v2/real-time/api/"


def psi_band(v: int) -> str:
    return ("Good", "Moderate", "Unhealthy", "Very unhealthy", "Hazardous")[
        (v > 50) + (v > 100) + (v > 200) + (v > 300)]


def fetch(lat: float, lon: float) -> dict:
    om = fetch_json(
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&timezone=Asia/Singapore&forecast_days=3"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m"
        "&hourly=temperature_2m,precipitation_probability,weather_code"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
        "precipitation_sum,uv_index_max,sunrise,sunset,wind_speed_10m_max,apparent_temperature_max",
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
