# NRF_EPD_5E5D — device notes

Living document. Everything we learn about this display goes here.

Status tags:
- **[verified]** observed on this exact unit
- **[source]** read in firmware source of a related project, not yet confirmed here
- **[online]** reported by someone else on similar hardware
- **[open]** unknown / to investigate

Last updated: 2026-10-16 (end of first session)

---

## 1. Hardware

| Item | Value | Status |
| --- | --- | --- |
| MCU | Nordic nRF52811 (firmware reports `nrf52811`) | [verified] |
| Panel | 4.2", 400×300 | [verified] (full-frame 400×300 image fills screen) |
| Colours | Black / white / **red** — red is drawn by the firmware's built-in calendar | [verified] |
| Panel controller | Unknown. Firmware model id `0x16` is not in any public source. Similar tags use SSD1619 (BWR) or UC8176 | [open] |
| Battery | 1100 mAh Li-ion (per owner) | [verified by owner] |
| Battery telemetry | Firmware reports `bat=<mV>`; reads 2921–2932 mV. Almost certainly the **regulated VDD rail**, not the cell (a Li-ion at 2.9 V would be cut off). Useful only as a "rail is sagging → battery low" signal | [verified] reading / [open] exact regulator |
| Debug | No SWD probe attached; all access over BLE | — |

## 2. Firmware

A **non-public variant** of [tsl0922/EPD-nRF5](https://github.com/tsl0922/EPD-nRF5). It matches neither upstream nor any fork we checked (incl. [YCD12/EPD-nRF5_DYC](https://github.com/YCD12/EPD-nRF5_DYC)).

| Item | Value | Status |
| --- | --- | --- |
| Version characteristic (`62750003`) | String `v1.10-nrf52811\0` (upstream returns one byte, e.g. `0x1a`; DYC `0x20`) | [verified] |
| BLE name | `NRF_EPD_5E5D` (upstream: `NRF_EPD_` + last 2 bytes of MAC) | [verified] |
| Image transfer RLE | Supported (`rle=1`) | [verified] |
| MTU | 247 negotiated, firmware reports `mtu=244` → 242 bytes image data per packet | [verified] |
| OTA | Nordic **Secure DFU** service `FE59` (buttonless) present. Signing key unknown → do **not** attempt | [verified] presence |
| Image "slots" | Notifies `slots=15 0 255` — likely 15 on-flash image slots; command set unknown | [open] |
| `sid=` | 64-hex-char ID (`F9196A6B…BA15`), looks like a SHA-256 — device/serial hash? | [open] |

### 2.1 Notifications sent after `INIT` (0x01)

Observed in order:

1. Raw config bytes (14 bytes, see §3) — sent when notifications are enabled
2. `slots=15 0 255`
3. `sid=<64 hex>`
4. `mtu=244 rle=1`
5. `t=<device local unix time> bat=<mV>` — `t` is local time (UTC + tz), e.g. Singapore adds 28800

## 3. Config block (14 bytes)

Current: `14 13 06 05 04 03 02 16 ff 12 07 01 00 04`

| Byte | Upstream meaning | Value here | Status |
| --- | --- | --- | --- |
| 0 | MOSI pin | `0x14` (P0.20) | [source] meaning |
| 1 | SCLK pin | `0x13` (P0.19) | [source] |
| 2 | CS pin | `0x06` | [source] |
| 3 | DC pin | `0x05` | [source] |
| 4 | RST pin | `0x04` | [source] |
| 5 | BUSY pin | `0x03` | [source] |
| 6 | BS pin | `0x02` | [source] |
| 7 | Model id | `0x16` (unknown upstream) | [open] |
| 8 | Wake-up pin | `0xFF` (none → keeps advertising, never deep-sleeps) | [source] |
| 9 | LED pin | `0x12` | [source] |
| 10 | EN (panel power) pin | `0x07` | [source] |
| 11 | **Display mode** — 0 picture, 1 calendar, 2 clock | was `0x02` (clock) out of the box; we set `0x01` | [verified] |
| 12 | Week start (0 = Sunday) | `0x00` | [source] |
| 13 | Not in upstream | was `0xFF`, became `0x04` after our first `SET_TIME` + `SET_CONFIG` | [open] |

Pins match upstream's built-in `EPD_CFG_52811` default.

## 4. BLE protocol

Service `62750001-d828-918d-fb46-b6c11c675aec`
- `62750002` — command/data: write, write-without-response, notify
- `62750003` — version: read

Every write is `[cmd][args…]`.

| Cmd | Name | Args | Behaviour | Status |
| --- | --- | --- | --- | --- |
| `0x00` | SET_PINS | 7–8 pin bytes | Saves pin map to flash | [source] — don't touch |
| `0x01` | INIT | optional model id | Initialises panel driver, replies with notifications (§2.1). **Never pass a model id** — it is persisted | [verified] |
| `0x02` | CLEAR | optional refresh flag | Full white clear + refresh, sets mode = picture. Online report: on SSD1619 it also powers the driver down, so send INIT again before image data | [verified] / [online] |
| `0x03` | SEND_CMD | 1 byte | Raw command to panel controller | [source] |
| `0x04` | SEND_DATA | bytes | Raw data to panel controller | [source] |
| `0x05` | REFRESH | — | Displays RAM contents, sets mode = picture | [verified] |
| `0x06` | SLEEP | — | Panel deep sleep | [source] |
| `0x20` | SET_TIME | `u32 BE unix ts`, `i8 tz hours`, `u8 mode` | Sets RTC, sets display mode, **forces a built-in redraw** (full refresh). The redraw runs **asynchronously** (app scheduler), so anything sent within ~25 s can interleave with it (we saw a mixed screen with the built-in `NRF_EPD_5E5D` label) | [verified] |
| `0x21` | SET_WEEK_START | `u8 0–6` | Calendar week start | [source] |
| `0x30` | WRITE_IMAGE | `flags`, data | Writes image RAM. See §5 | [verified] partially |
| `0x31–0x33` | WRITE_BLOCK / QUERY_STATUS / RESET_TRANSFER | CRC'd block transfer | Exists in DYC fork only | [open] on this unit |
| `0x90` | SET_CONFIG | 14 config bytes | Overwrites config in flash, **no redraw**. Read config first, change one byte, write back | [verified] |
| `0x91` | SYS_RESET | — | Reboot | [source] |
| `0x92` | SYS_SLEEP | — | System-off deep sleep. With wake-up pin `0xFF` there may be no way to wake it except power-cycling | [source] — avoid |
| `0x99` | CFG_ERASE | — | Erase config + reboot. Default config for nRF52811 would **not** contain model `0x16` → likely breaks display | [source] — avoid |

## 5. Image transfer

Frame = 400×300 at 1 bit per pixel, MSB first, row-major → 15 000 bytes per plane.

### 5.1 Modern flags (upstream v1.6+) — what we use for black/white

`flags` bit 0 = 0 black plane / 1 red plane, bit 1 = first chunk, bit 2 = RLE-compressed.
RLE: control byte `0x80|(n-3)` + value = run of n (3–130); control `n-1` + n bytes = literal. Each packet must contain whole RLE codes.

| Finding | Status |
| --- | --- |
| **Disconnecting powers the panel down mid-refresh.** A full refresh runs through flash, negative, black and (on red panels) long red phases. Disconnecting ~2 s after `REFRESH` froze the screen in whichever phase it was in: an inverted image, solid black, or blank. **Hold the connection ~30 s after `REFRESH`.** | [verified] 2026-10-16 |
| Polarity matches upstream: black plane `1 = white`, `0 = black`. (The "inverted polarity" we recorded earlier was a refresh frozen in its negative phase; flipping our data made the frozen negative look right.) | [verified] |
| A "red plane" (bit 0 = 1) appeared to overwrite black, but that test also disconnected mid-refresh, and red is the last, slowest phase. **Needs retesting with the 30 s hold.** | [open] |
| **The panel keeps a separate red RAM.** Pushing only the black plane without `CLEAR` showed a dithered red overlay: stale red RAM from earlier tests. Sending an all-`0xFF` red plane (= no red) on every push fixes it, with no `CLEAR` needed. | [verified] 2026-10-16 |
| Matches the SSD1619A datasheet: `0x24` BW RAM (1 = white), `0x26` red RAM with a "Display Update Control 1" option to invert it; upstream inverts it, so 0 = red. The datasheet also says: *"User should not interrupt this operation to avoid corruption of panel images."* | [source] |
| `CLEAR` (0x02) is **not** needed per push: black plane + blank red plane + full `REFRESH` held to completion comes out clean (~40 s per push vs ~70 s). Keep an occasional `CLEAR` for ghosting. If you do `CLEAR`, wait ~25 s before sending `INIT` (INIT hardware-resets the panel and would cut the clear's refresh short) | [verified] 2026-10-16 |
| Rendering: anti-aliased text thresholded at luminance 170 (not 128) keeps small strokes solid on the panel | [verified] |
| A `SET_TIME` built-in calendar redraw is **not** a good enough wipe; with a 15 s wait the next upload came out messy | [verified] |

### 5.2 Legacy flags (pre-v1.6)

Low nibble `0x0F` = black plane, `0x00` = red plane; high nibble `0xF0` on every chunk after the first. No RLE. Polarity per online report: `1 = white`, `0 = ink` in both planes.

| Finding | Status |
| --- | --- |
| Used successfully for black+red on an nRF52811 400×300 SSD1619 tag with DYC firmware ([epd-ai-quota-display](https://github.com/askfanxiaojun/epd-ai-quota-display/blob/main/docs/BLE_PROTOCOL.md)) | [online] |
| **Not supported on this unit.** The firmware parses the flag byte with the modern bit layout, so `0x0F` = red + begin + RLE. Raw bytes got RLE-decoded → shifted, wrapped garbage ("RED" split across both edges) | [verified] 2026-10-16 |

### 5.3 Red on uploads — conclusion so far

**Superseded:** every red test below disconnected ~2 s after `REFRESH`, so none of them let the red phase run. The conclusions are unreliable. Retest the modern red plane with the 30 s hold first. [open]

Raw controller probes via `SEND_CMD`/`SEND_DATA` (0x03/0x04), 2026-10-16. Each ran after `CLEAR` + 25 s + `INIT`, a normal black-plane upload (except probe 2), then `REFRESH`:

| Probe | Raw sequence | Result |
| --- | --- | --- |
| 1. SSD1619 red RAM | `0x11 03`, `0x44 00 31`, `0x45 00 00 2B 01`, `0x4E 00`, `0x4F 00 00`, `0x26` + red plane | **Blank screen**, black plane lost too [verified] |
| 2. UC8176 KWR mode | `0x00 0F` (PSR), `0x50 77` (CDI), `0x10` + B/W plane, `0x13` + red plane | **Blank screen** [verified] |

In both cases a normal push afterwards worked fine, so the probes did no lasting harm. The blank results are best explained by the cut-short refresh (§5.1), not by the raw commands.

## 6. Built-in display modes

| Mode | Behaviour | Status |
| --- | --- | --- |
| Picture (0) | Shows last uploaded image. Firmware never redraws on its own | [verified] |
| Calendar (1) | Firmware-rendered month calendar (Chinese lunar dates, solar terms, holidays); uses red. Redraws at **local midnight** | [verified] red / [source] midnight |
| Clock (2) | Firmware-rendered clock + date. **Full refresh every minute** (flashes, drains battery). Upstream's web tool warns before enabling it that clock mode uses full refreshes and isn't recommended long-term. It can't show an uploaded picture: the minute timer redraws the built-in layout | [source] |
| Time-sync hint | If the RTC reads January 2025 (never set), built-in views show a "sync time" tip | [source] |
| After reboot | Firmware redraws the current mode immediately; after a watchdog reset it forces calendar | [source] |

### 6.0 Live clock on our own dashboard: not possible with this firmware

| Finding | Status |
| --- | --- |
| The only self-updating time is clock mode (built-in layout, full refresh every minute) | [source] |
| Upstream "partial" code (`PTIN`/`PTL`/`PTOUT` in UC81xx.c) only windows RAM *writes*; refreshes are always full-screen | [source] |
| [zhyiheihei/EPD-nRF5](https://github.com/zhyiheihei/EPD-nRF5) adds `UC81xx_RefreshPartial` (PTIN + `PT_SCAN=1` window + DRF, ~4 s waveform, BUSY not released on their BWR panel) behind a custom dashboard protocol (`0x40`–`0x46`). It's custom firmware for a 7.5" UC8179, so not usable here without flashing | [online] |
| Partial refresh via raw `SEND_CMD`/`SEND_DATA` from the host is untested on this unit (our earlier raw probes were invalidated by the cut-short-refresh bug, §5.3) | [open] |
| Decision (owner): no live clock. The dashboards show a small "last updated" stamp instead | — |

### 6.1 Clock

| Finding | Status |
| --- | --- |
| No battery-backed RTC chip: a 1 s app_timer (nRF low-frequency clock) increments a counter | [source] |
| Only set by `SET_TIME` over BLE; stores **local** time (UTC + tz offset) | [verified] |
| Power-on default is 2025-01-01 00:00 (first read: `t=1735690069`, i.e. ~8 min after boot). Lost on reset or battery loss | [verified] |
| Right after sync it matched the Mac within 1 s | [verified] |
| Drift: depends on whether the board has a 32 kHz crystal (~±20 ppm ≈ 2 s/day) or uses the internal RC oscillator (much worse). Measure by comparing `t=` against host time across pushes | [open] |
| Measured offset −4 s on two pushes ~15 min apart → the −4 s is mostly measurement latency (`t=` is sent at INIT, host time is read ~1–4 s later); real drift is small so far | [verified] preliminary |

## 7. How we use it (this repo)

See the [README](../README.md) for the software. Pushes are scheduled by homelab-hq (every 30 min 07:00–23:00, wipe at 06:55); see README "Scheduling". `uv run python tools/info.py` dumps everything the device reports (version, decoded config, battery, clock drift).


- Host (Mac) renders screens with Pillow and pushes over BLE (bleak). The display is **passive** and never fetches anything on its own.
- Each push: connect (read `bat`, `t`) → if clock drift > 30 s: `SET_TIME(calendar)` + 25 s → `CLEAR` + 25 s → `INIT` → black plane → `REFRESH` → `SET_CONFIG(display_mode = calendar)`.
- **Dead-man fallback:** the last step re-arms calendar mode without redrawing. If pushes stop, the firmware replaces our picture with its own calendar at the next local midnight — the same moment the today/tomorrow forecast becomes wrong. [verified config write; midnight switch not yet observed]
- If the Mac can reach the device but the weather fetch fails, we show the built-in calendar instead of a stale forecast.
- **Why calendar and not clock as the fallback:** the firmware's timer checks every second, and in clock mode it redraws on every minute boundary. Arming clock mode would replace our picture within 60 s, so clock can't sit dormant behind a pushed image. Calendar's only trigger is local midnight, so it can.
- Location: Punggol (1.4043, 103.9021). The NEA 2-hour area and PSI region are chosen by nearest label location (Punggol → area "Punggol", PSI region "east").

## 8. BLE behaviour

| Finding | Status |
| --- | --- |
| Advertises intermittently; scans can take 30–45 s to find it | [verified] |
| macOS address (CoreBluetooth UUID): `D686F346-CBEE-3785-1FC7-6409492509FF` | [verified] |
| Only one central at a time: close the web tool before running scripts. A manual push during a scheduled one fails, so hold the hq job first | [online] / [verified] |
| Under launchd, CoreBluetooth permission belongs to the runner (`bun`), not the terminal: `BleakBluetoothNotAvailableError: Bluetooth access is denied` until `bun` is allowed in Privacy & Security → Bluetooth | [verified] 2026-10-16 |

## 9. Open questions

1. What is model `0x16`? Does the modern red plane work once the refresh is allowed to finish (§5.1, §5.3)?
2. What are the 15 "slots", and how do we use them? Could the device rotate stored images on its own?
3. What is `sid`, and what is config byte 13?
4. Does calendar mode really switch over at midnight on this variant? (Check the morning after a day without pushes.)

## Sources

- [tsl0922/EPD-nRF5](https://github.com/tsl0922/EPD-nRF5) — upstream firmware + web tool (protocol, RLE, modes)
- [YCD12/EPD-nRF5_DYC](https://github.com/YCD12/EPD-nRF5_DYC) — fork with legacy flags + CRC block transfer
- [askfanxiaojun/epd-ai-quota-display](https://github.com/askfanxiaojun/epd-ai-quota-display) — macOS + BLE pusher for a 400×300 BWR nRF52811 tag; legacy-flag protocol notes
- [jam422470459/EPD-nRF52-hema213](https://github.com/jam422470459/EPD-nRF52-hema213), [jyh9521/EPD-nRF5-JP](https://github.com/jyh9521/EPD-nRF5-JP) — other nRF52811 forks
