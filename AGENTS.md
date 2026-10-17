# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

Mac-side renderer and BLE pusher for a 4.2" 400×300 nRF52811 e-ink tag (`NRF_EPD_5E5D`). See README.md for usage and design history, and docs/DEVICE.md for everything known about the hardware and firmware.

## Commands

Python ≥ 3.11 via uv (deps: bleak, pillow). There is no test suite or linter. Verify visually instead.

```sh
uv run python -m epd.cli <layout> --preview out.png   # render without the device; add --bat 2800 to show BATT LOW
uv run python -m epd.cli --push                       # push current layout from config.toml (~40 s)
uv run python -m epd.cli --push --wipe                # full CLEAR first (~70 s), ~once a day for ghosting
uv run python -m epd.cli list | use <layout>          # list / switch layouts (rewrites config.toml)
uv run python tools/info.py                           # device config, battery, clock drift (read-only)
uv run python tools/screenshots.py                    # regenerate docs/images/*.png for the README
```

Workflow the owner expects: render a preview, look at it (Read the PNG, ideally upscaled 2× with NEAREST), fix overflows/alignment, then **show the owner the PNG (open it on screen) and wait for their OK before pushing a new or changed layout**. After pushing, ask how it looks on the panel. Previews are pixel-exact (`epd.image.preview` runs the same 1-bit conversion as a push). After layout changes, run `tools/screenshots.py` so the README gallery stays current.

## Architecture

Pipeline: `screens/weather.fetch()` → `screens/<layout>.render()` → `epd.image.to_planes()` → `epd.device.EPD.show()` → `arm_fallback()`.

- `epd/cli.py` owns the `SCREENS` registry (name → module). Every layout module exposes `fetch(lat, lon)` (all reuse `screens.weather.fetch`) and `render(data, now=None, battery_mv=None)`. `push()` connects **before** rendering so the frame can use the battery level the device reports on connect.
- `screens/weather.py` holds both the data fetch (Open-Meteo + NEA data.gov.sg, cached via `epd/data.py`) and the legacy `detailed` layout. `glance`/`rain` build on `screens/common.py`: `Forecast` (current/hourly/daily view, NEA nowcast override, rain windows, night), the shared header `canvas()`, fonts, and alignment helpers.
- `note` layout: `screens/note.fetch` adds `data["quip"]` from `screens/quip.py` (OpenRouter via `epd/llm.py`, key and model in gitignored `.env`; see `.env.example`). The quip is a haiku, validated (3 lines, fits the panel) and cached in `.cache/quip.json` by a forecast signature; failures fall back to `config.toml [note]`. The owner found playful one-liners "cheesy" and asked for haikus.
- `proverb` layout reuses `note.layout()` (the shared side-panel dashboard; panel width = `main_cols` of 6 hourly columns) with a 2/6 panel and today's entry from `data/proverbs.json` (366 entries keyed `MM-DD`). Any new entry must pass `note.panel_lines(...).fits` at that width.
- `screens/common.py` also holds the shared header `canvas()` (date + place left; tiny two-line "last updated / h:mm" stamp right, deliberately not clock-like) and `day_row()` (Today/Tmrw: label, icon, high/low, 24 h rain sparkline, rain %), used by glance/note/proverb. Change them once, and they change everywhere.
- `config.toml` holds the current layout and location. `epd.cli use` rewrites only its `screen =` line.
- **Scheduling lives in homelab-hq** (`~/Developer/potateros/homelab-hq/jobs.toml`): `eink-weather` runs `uv run python -m epd.cli --push` every 30 min outside 23:00–07:00, and `eink-wipe` runs `--push --wipe` at 06:55. Scheduled pushes use whatever `config.toml` says. Before long manual BLE sessions run `hq hold eink-weather` (one central at a time), then `hq resume eink-weather`. Logs: `hq logs eink-weather`. Bluetooth access is granted to `~/.bun/bin/bun` (launchd's responsible process), not the terminal. To add or change jobs, use the hq-add-job skill.
- `epd/device.py` speaks the EPD-nRF5 BLE protocol (service `62750001-…`, write `62750002`, version `62750003`): INIT, CLEAR, RLE image upload (`0x30`, modern flag bits), REFRESH, SET_TIME, SET_CONFIG.

## Device rules (learned the hard way, see docs/DEVICE.md)

- After `REFRESH`, **hold the connection ~30 s**. Disconnecting powers the panel down mid-refresh and freezes it inverted, black, or blank. This was behind many early "polarity"/"red doesn't work" misdiagnoses.
- Always send a red plane too (all `0xFF` = no red) or stale red RAM shows through. Polarity is upstream's: 1 = white.
- After `CLEAR`, wait ~25 s before `INIT` (INIT hardware-resets the panel). `SET_TIME` forces an asynchronous built-in redraw, so don't upload within ~25 s of it, and it's not a valid wipe.
- Every push ends with `SET_CONFIG` setting display_mode = calendar: a dead-man fallback so the firmware's own calendar replaces a stale forecast at local midnight. Read the 14-byte config first and change only byte 11.
- Never pass a model id to `INIT` (it's persisted). Avoid `0x92` (sys sleep; wake-up pin is `0xFF`), `0x99` (config erase; defaults lack model `0x16`), raw `0x00` SET_PINS, and DFU. The firmware is a non-public variant.
- The device accepts one BLE central at a time, and it advertises intermittently (scans up to 45 s).
- Battery `bat=` is the ~3.0 V rail, not the Li-ion cell. Show it as an estimated `~NN%` from the firmware's own curve (`screens.weather.battery_pct`, same as the built-in calendar's glyph), red + LOW below 30 %. Every push logs the reading to `.cache/battery.csv`; previews reuse the last one.

## Rendering rules

- Solid black, white and red only: draw with `ImageDraw.fontmode = "1"` (no anti-aliasing) and solid shapes. No dithered text. Red (`screens.common.RED`) is a signal colour for actionable items only (wet hours ≥ `WET`, haze, battery LOW); pushes and previews use `to_planes`/`preview(..., red=True)`.
- Fonts are vendored in `fonts/` (TRMNL framework, OFL). Pixel fonts render cleanly only at native sizes, so always go through `screens.common` (`bold()`, `medium()`), which snap sizes: TRMNL12/16/21 Bold for numbers, the date and the condition; NicoClean (`medium`) for body text; Inter Bold from 26 px. The owner rejected Helvetica (breaks up), Menlo/Monaspace (monospace, or uneven at 1 bit), Verdana (too heavy), thin regular weights, and a double-strike medium (uneven).
- Position text with `text_mid` (cap-height centred), `text_top` (cap top on a line) and `icon_mid`, not raw `d.text` offsets, so rows share centre lines. The owner tunes alignment at the pixel level.
- Layout content rules: readability over completeness; haze line only when PSI > 100; long conditions wrap (`wrap()`) rather than shrink.
- **Battery meter on every dashboard, always in the same place: the top-right corner of the header**, modelled on the firmware calendar's own battery glyph (outline, nub, fill bar). The owner wants a percentage, or at least an estimate good enough to decide when to charge. Draw it once in `screens.common.canvas()` so every layout gets it; any new layout must keep it. (Replaces the old "battery only when LOW" rule.)

## Docs

`docs/DEVICE.md` is a living reference: record every new device finding there, tagged [verified] / [source] / [online] / [open]. Update README.md when layouts, commands or design decisions change.
