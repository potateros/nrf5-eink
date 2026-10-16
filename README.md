# nrf5-eink

A TRMNL-style dashboard for a cheap 4.2" Bluetooth e-ink tag (nRF52811, 400×300).
The Mac renders screens with Pillow and pushes them over BLE. The display itself is passive.

- **Device reference (hardware, firmware, BLE protocol, quirks):** [docs/DEVICE.md](docs/DEVICE.md)
- **Device:** `NRF_EPD_5E5D`, a non-public variant of [tsl0922/EPD-nRF5](https://github.com/tsl0922/EPD-nRF5) firmware (`v1.10-nrf52811`)

## Quick start

```sh
uv run python -m epd.cli weather --preview out.png   # render only (add --bat 2921 to draw the battery icon)
uv run python -m epd.cli weather --push              # send to the display (~40 s)
uv run python -m epd.cli weather --push --wipe       # full clear first (~70 s); ~once a day for ghosting
uv run python tools/info.py                          # what the device reports (config, battery, clock)
uv run python tools/testcard.py                      # black/white test card
```

Requirements: macOS with Bluetooth, [uv](https://docs.astral.sh/uv/). Dependencies: `bleak`, `pillow`.
Close any browser/web-tool connection to the display first; it accepts one central at a time.

## Layout

```
epd/
  device.py   BLE client: connect, INIT, image upload (RLE), CLEAR, SET_TIME, SET_CONFIG, clock drift
  image.py    PIL image -> 1-bit planes (+ preview)
  rle.py      RLE codec matching the firmware
  data.py     cached JSON fetcher (data.gov.sg rate-limits hard; falls back to the last good copy)
  icons.py    weather glyphs drawn with PIL primitives (crisp at 1 bit), WMO + NEA text -> icon
  cli.py      `python -m epd.cli <screen> [--preview PNG] [--push] [--wipe] [--lat/--lon] [--bat mV]`
screens/
  weather.py  today + tomorrow forecast screen
tools/
  info.py, testcard.py
  experiments/  failed red-colour probes, kept for the record
docs/DEVICE.md  everything known about the device
```

## How a push works

1. Scan for `NRF_EPD*` (up to 45 s; it advertises intermittently) and connect.
2. `INIT` → the device notifies config, `slots`, `sid`, `mtu`, `t=<local time> bat=<mV>`.
3. Render the screen, drawing in the battery level it just reported.
4. If the device clock is more than 30 s off: `SET_TIME`, then wait 25 s (it triggers a built-in redraw that runs in the background).
5. (`--wipe` only) `CLEAR`, wait 25 s → `INIT` → black plane + all-white red plane → `REFRESH` → **hold the connection 30 s** (disconnecting powers the panel down mid-refresh).
6. `SET_CONFIG` with display_mode = calendar: the **dead-man fallback** (below).

If the data fetch fails but the device is reachable, it shows the firmware's built-in calendar instead of a stale forecast.

### Dead-man fallback

The display can't detect staleness itself. But the firmware redraws its own calendar at **local midnight** when in calendar mode. So every push leaves the picture on screen with calendar mode armed. If pushes stop, the built-in date view takes over at midnight, exactly when the "Today/Tmrw" forecast becomes wrong. Clock mode can't be armed this way: it redraws every minute and would replace the picture immediately. See DEVICE.md §7.

## Weather screen

Location: **Punggol** (1.4043, 103.9021).

| Area | Content | Source |
| --- | --- | --- |
| Header (black on white) | Date · place · "updated h:mm" · battery OK/LOW | local clock, device `bat=` |
| Now | Icon, big temperature, feels-like; NEA 2-hour forecast for the area ("Cloudy until 5.00 pm"); humidity, wind; one air line (PSI + band) | Open-Meteo current, NEA 2-hr forecast, NEA PSI (nearest region → East) |
| Hourly | 8 slots, 2 h apart: hour, icon, temperature, chance-of-rain bar + % | Open-Meteo hourly |
| Today / Tmrw | Icon, high/low, rain chance + mm (bold 14 pt), NEA forecast text, UV, sunset | Open-Meteo daily + NEA 24-h forecast / 4-day outlook |

Data notes:
- data.gov.sg (`api-open.data.gov.sg/v2/real-time/api/…`) needs a User-Agent and rate-limits at a few requests per ~10 s. Responses are cached in `.cache/`.
- NEA has no rain percentage. Rain % and mm come from Open-Meteo's model.
- Open-Meteo's PM2.5 model badly underestimated the Oct 2026 haze (≈83 vs NEA's measured 182 µg/m³), so air quality uses NEA only.
- The NEA nowcast overrides the model's current condition (the model said "Mostly clear" during showers).

### Design decisions (from the owner)

- Weather first. Air quality is one line, not the focus (even during the haze).
- Header is black text on white with a rule underneath. White on black was hard to read.
- Battery shows **OK / LOW**, not a percentage. The firmware measures the ~3.0 V regulated rail (≈2.92 V), not the 1100 mAh Li-ion cell, so a % would be fiction. LOW below 2.85 V.
- Spacing tuned on the real panel: big temp at `y0+3`, "Feels" at `y0+58`, condition title top-aligned with the digits, hourly labels 10 px below the divider, "TMRW" instead of "TOMORROW".

## Panel constraints

- Uploads are **black/white only**. The panel can show red (the firmware's calendar uses it), but every way of uploading red failed. See DEVICE.md §5.3.
- Every update is a full refresh with flashing. A wipe plus draw takes about 1 minute end to end.
- 400×300 at 1 bit; no grey. Avoid dithering text. Use solid shapes and hatching.

## Ideas / backlog

- [ ] launchd job: push weather every 30–60 min while the Mac is awake
- [ ] Rotating screens: agenda (macOS Calendar / ICS), month calendar, fun slot
- [ ] Haze alert screen: full-screen warning if PSI > 300
- [ ] Clock options: firmware clock (flashes every minute, battery weeks to months), or a big-time weather variant pushed every 15 min, or clock mode at night only
- [ ] Fun slots: bus/MRT arrivals (LTA DataMall key), dithered photo, xkcd, GitHub contributions, quote of the day, a Claude-written daily summary
- [ ] Investigate the firmware's 15 image "slots": could the device rotate stored images on its own?
- [ ] Measure clock drift over a day (log `t=` vs host time)
