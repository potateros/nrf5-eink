# NRF_EPD_5E5D: capabilities

Everything this board and panel can and can't do, as of 2026-10-16. Each row has a status:
**[verified]** seen on this unit · **[source]** from upstream firmware source · **[open]** unknown.
For protocol details and the history behind each finding, see [DEVICE.md](DEVICE.md).

## Summary

- **Three colours work on uploads:** black, white and red, crisp down to 1 px lines and 16 px text. [verified]
- **Every update is a full refresh of about 22 s** (flashes, then saturates red). No partial or fast refresh. [verified]
- **The device is passive:** it shows what was pushed, or its own calendar/clock. It can't fetch anything.
- **It can't report back** beyond a few values at connect: config, slot mask, ID, MTU, local time, rail voltage.
- **Its own calendar takes over at midnight** when armed, which is our fallback if pushes stop. [verified]

## Display

| Capability | Detail | Status |
| --- | --- | --- |
| Resolution | 400×300, 1 bit per pixel per plane, full frame only via `0x30` | [verified] |
| Colours | Black, white, **red**. No grey and no shades of red: anything else must be dithered, which breaks text | [verified] |
| Red on uploads | Works with the modern `0x30` flag (bit 0 = red plane), red plane 0 = red, `0xFF` = no red. Solid fills, 3 px stripes, 1 px lines, 16 px NicoClean and 21 px TRMNL Bold text all render sharp. Webcam-checked: `tools/experiments/red_card.py` | [verified] 2026-10-16 |
| Red + black overlap | If a pixel is 0 in both planes, red wins (SSD16xx red RAM overrides BW). `epd.image.to_planes` never produces that overlap | [source] |
| Red appearance | Saturated darker red, readable as well as black at the same size; thin red strokes look slightly lighter than black ones | [verified] |
| Controller | **SSD16xx command set (SSD1619-compatible).** A red box written through raw `0x26` (red RAM) appeared after REFRESH: `tools/experiments/raw_ssd1619_probe.py`. Model id `0x16` is this variant's own id for it | [verified] 2026-10-16 |
| Refresh | Full refresh only, about **22 s**: flash and inversion (~0–8 s), black/white settle (~14 s), red saturates (~18 s), done (~22 s). Measured from REFRESH at 1 fps on the webcam | [verified] |
| Refresh is asynchronous | Unlike upstream (which blocks the BLE handler until BUSY clears), this firmware answers ~0.2 s after REFRESH. **The connection must still be held**: disconnecting powers the panel down and freezes the refresh mid-phase | [verified] |
| Hold after REFRESH | 30 s (≈8 s margin over the measured 22 s). Don't shorten below ~25 s | [verified] |
| Ghosting | A black/white/red push straight over a different image came out clean with no CLEAR. A daily CLEAR remains good practice | [verified] |
| Partial / fast refresh | Not available to us. Upstream's "partial" code only windows RAM writes. A fast mode would need a custom LUT (`0x32`), which is risky on an unknown panel and not attempted. The seller says the variant's built-in clock uses partial refresh (DEVICE.md §2.0), but there's no known command for our own images | [source] / [online] / not attempted |
| Temperature sensor | The controller has one and upstream reads it before each refresh, but nothing reports it over BLE | [source] |
| Panel sleep | `0x06` puts the controller in deep sleep; the firmware also does this on disconnect | [source] |

## Built-in screens (firmware-drawn)

| Mode | What it does | Status |
| --- | --- | --- |
| Picture (0) | Keeps the last uploaded image; never redraws on its own | [verified] |
| Calendar (1) | Month calendar with lunar dates, solar terms and holidays, with red; `2.9V` + battery glyph top right. Redraws at device-local 00:00:00, replacing a pushed picture when armed by SET_CONFIG: our dead-man fallback | [verified] 2026-10-16 (webcam, clock set to 23:58) |
| Clock (2) | Clock + date, temperature, ISO week, next solar term. Upstream: full refresh every minute; seller: partial refresh on this variant. Not for long-term use (burn-in warning). Upstream's tool suggests it to repair ghosting on aged screens | [source] / [online] |
| Week start | `0x21`, 0 = Sunday … 6 | [source] |

## Board

| Capability | Detail | Status |
| --- | --- | --- |
| MCU | nRF52811 (Cortex-M4, 192 KB flash, 24 KB RAM), firmware `v1.10-nrf52811` | [verified] |
| Clock | Software RTC (1 s timer). Set only by `SET_TIME`; lost on reset (back to 2025-01-01). Sync is good to ±1 s (the timer keeps its sub-second phase). Offset measurable to ±0.15 s with `tools/experiments/clock_offset.py`. Runs fast by ~+120 ppm (±60), ~5–15 s/day: internal RC oscillator, no 32 kHz crystal. Pushes resync past 30 s, so every few days | [verified] 2026-10-16 |
| Battery telemetry | `bat=` is the ~3.0 V rail (2.91–2.93 V), not the 1100 mAh cell. Shown as an estimated % via the firmware's `batt_cal` curve (≈ 68 %), matching the calendar's glyph; it stays flat most of the cell's life and drops near the end. Logged per push to `.cache/battery.csv` | [verified] |
| LED | Pin `0x12` in config. Upstream lights it during BUSY. A blue glow is visible on camera during refreshes | [source] / [verified] glow |
| Buttons / wake pin | None configured (wake-up pin `0xFF`), so it advertises all the time and never deep-sleeps | [verified] config |
| Storage slots + carousel | Notification `slots=15 <mask> 255` = count, used bitmask, current slot. Commands from the myetoys web tool (DEVICE.md §2.0b): `0x31 [0,n]` stores the next upload in slot n, `0x31 [1,n]` shows it, `0x32 [n]` deletes it, `0x33 [min_hi,min_lo]` rotates through stored images every N minutes, with no Mac needed. 15 full frames can't fit in 192 KB of flash, so they are compressed or external | [verified] values / [source] commands, untested |
| `sid` | 64 hex chars, constant across connections (`F9196A6B…BA15`) | [verified] / [open] meaning |

### Battery life (estimate)

Power budget on the current schedule (33 pushes/day: every 30 min 07:00–23:00 plus the 00:01 re-push), from typical part figures. These are not measured on this board: no current meter, and `bat=` is the regulated rail.

| Case | Per push (22 s refresh + ~45 s connected) | Idle (advertising, no wake pin) | Per day | Full 1100 mAh charge (85 % usable, ~2 %/month self-discharge) |
| --- | --- | --- | --- | --- |
| Low | 5 mA refresh, 0.6 mA link: 0.04 mAh | 15 µA | 1.6 mAh | ~13 months |
| Typical | 8 mA, 1 mA: 0.06 mAh | 30 µA | 2.8 mAh | **~9 months** |
| High | 12 mA, 2 mA: 0.10 mAh | 80 µA | 5.3 mAh | ~5 months |

**So: charge roughly every 6 months to be safe**, or when the header meter turns red (the rail only sags in the last few percent, so red means charge within days). Pushes dominate: halving the schedule (hourly) would add roughly 40 % more life. [estimate]

## Bluetooth

| Capability | Detail | Status |
| --- | --- | --- |
| Name / address | `NRF_EPD_5E5D`, macOS UUID `D686F346-CBEE-3785-1FC7-6409492509FF` | [verified] |
| Throughput | MTU 247, 242-byte image packets, RLE (`rle=1`). A typical dashboard uploads in a few seconds | [verified] |
| Centrals | One at a time. Advertises intermittently; scans take up to ~45 s | [verified] |
| GATT | `62750001` service: `62750002` write / write-without-response / notify (CCCD h=14), `62750003` read = `v1.10-nrf52811\0`. `FE59` Nordic Buttonless Secure DFU (`8ec90003`, indicate + write) | [verified] 2026-10-16 |
| Readback | None. Raw `SEND_CMD`/`SEND_DATA` (`0x03`/`0x04`) are write-only, so controller registers, temperature and RAM can't be read | [source] |
| OTA | Secure DFU present; signing key unknown. Don't attempt | [verified] presence |

## Commands

| Cmd | Use | Safe? |
| --- | --- | --- |
| `0x01` INIT | Connect handshake; no argument (an id would be persisted) | yes |
| `0x02` CLEAR | Full white wipe; wait ~25 s before INIT | yes |
| `0x03`/`0x04` SEND_CMD/DATA | Raw controller access. RAM commands (`0x11`, `0x44`, `0x45`, `0x4E`, `0x4F`, `0x24`, `0x26`) are safe | RAM-only |
| `0x05` REFRESH | Show RAM, hold 30 s | yes |
| `0x20` SET_TIME | Sets clock + mode, forces a built-in redraw (async, ~25 s) | yes |
| `0x21` SET_WEEK_START | Calendar week start | yes |
| `0x30` WRITE_IMAGE | Planes; flags bit 0 red, bit 1 begin, bit 2 RLE | yes |
| `0x90` SET_CONFIG | Read the 14 bytes first, change one byte | carefully |
| `0x00` SET_PINS, `0x91` reset | Pin map / reboot | avoid / ok |
| `0x92` SYS_SLEEP | No wake pin, so it may never wake | **never** |
| `0x99` CFG_ERASE | Defaults lack model `0x16` | **never** |
| Raw controller `0x2A 0x30 0x36 0x39` (OTP), `0x32` (LUT), `0x03 0x04 0x2C` (voltages) | One-time-programmable or panel-damaging | **never** |
| Unknown opcodes | Owner-approved probe 2026-10-16 (`tools/experiments/opcode_probe.py`): `0x31`–`0x4F` sent alone (no arguments), twice. No notification, no config or slots change, no redraw on the webcam, device healthy after. So they're unused, or need arguments (handlers often return early on short writes). Probing with arguments was stopped by the session's permission check (could be an irreversible flash write) and is the owner's call. Other ranges untried | probed: no-arg only |

## How to draw red

```python
from epd.image import RED, to_planes      # RED = (220, 0, 0)
d.fontmode = "1"                          # no anti-aliasing, as for black
d.text(xy, "Rain 6pm", font=bold(21), fill=RED)
black, red = to_planes(img, red=True, dither=False)
await epd.show(black, red)                # EPD.show already sends both planes and holds 30 s
```

`epd.image.preview(img, red=True, dither=False)` shows exactly what the panel gets. Since 2026-10-16 `epd/cli.py` pushes and previews every layout with red (accents for wet hours, haze and battery LOW; see README design decisions).

## Image slots and carousel

From the myetoys web tool (DEVICE.md §2.0b), **verified on this unit 2026-10-17** (§2.0c): store, show and carousel work with full frames, and a normal push ends a carousel.

### How to use them

| Goal | Commands |
| --- | --- |
| Store a frame in slot n | `0x31 [0, n]`, then the normal `INIT` → image chunks → `REFRESH` (so storing also displays it) |
| Show slot n | `0x31 [1, n]`, then `SET_TIME` mode 0 (picture). One short write instead of a ~10 s upload; the panel still does a full refresh, so the 30 s hold still applies |
| Delete slot n | `0x32 [n]` (irreversible) |
| Rotate through used slots | `0x33 [min >> 8, min & 0xFF]`. Runs on the device, no Mac needed. Any `SET_TIME` mode change stops it |

From a phone, the myetoys web tool (Chrome on Android, Bluefy on iOS) has buttons for all four, so stored screens can be switched without the Mac.

### What it's good for

The weather dashboards don't gain much. They are live data the Mac already pushes every 30 min, and a stored forecast goes stale. The firmware's own midnight calendar is a better fallback than an old forecast on loop. Where slots do help:

1. **Static screens, switchable from the phone.** Store a few that never go stale (guest Wi-Fi QR, "in a meeting / do not disturb", "away until …", a photo or poster) and flip to one from the phone's web tool, wherever the Mac is. **Catch:** showing slot n makes n the target for the next upload (byte 13), so the next scheduled push overwrites it. This only works if pushes write to a reserved scratch slot (`0x31 [0, 14]` before each upload) or the schedule is paused.
2. **Away / offline mode.** Before a trip, fill the slots with timeless content (proverbs, art, photos, xkcd) and start a carousel every few hours. The panel stays alive with no Mac and no BLE sessions. Each change is still a full refresh, so battery use is about the same per change as a push minus the ~45 s BLE link.
3. **Two live layouts on one panel.** Each push stores the weather layout in slot 0 and the agenda in slot 1, then ends with `SET_SLIDE 15` instead of the calendar fallback. The panel alternates on its own between pushes. The cost is the midnight dead-man: if the Mac stops, two stale frames rotate forever.

### Unknowns

- ~~Plain uploads~~: every push is stored in the current slot (byte 13) [verified]. That's one slot rewritten ~33 times a day; see the wear estimate in DEVICE.md §2.0c.
- ~~Current slot~~: byte 13 [verified].
- **Carousel lifetime:** a normal push ends it [verified]; the midnight redraw and a power cycle are untested.
- **Store vs display:** storing always displays the frame too (the upload ends with REFRESH). So use 3 means visible refreshes for each stored layout.

## Open

1. **Slots:** the commands were found on 2026-10-17 in the myetoys build of the web tool (DEVICE.md §2.0b), which reopens the 2026-10-16 "leave it" decision. Still open: what fills them without `SET_SLOT` (the mask went 0 → `0x7FFF` across a day of plain pushes), what they hold, which field is "current", and how a carousel interacts with our `SET_CONFIG` fallback and the midnight redraw. Testing needs device writes (owner's call).
2. ~~`sid`~~: a licence ID the myetoys tool sends to a paid template renderer (DEVICE.md §2). Old notes: `sid` (constant 64-hex, SHA-256-sized; not SHA-256/SHA3/BLAKE2s of the name, `5E5D` or the version string; the advertising data carries only the name and service UUID, so the MAC/FICR ID it may hash can't be read over BLE) and config byte 13 (`0x04`, variant-only: upstream's config is 13 bytes; unchanged by every command we send). Neither can be decoded without the firmware image.
3. ~~Midnight switch~~: verified 2026-10-16.
4. ~~Battery days left~~: estimated from a power budget (see Battery life below). `.cache/battery.csv` will refine it when the rail starts to sag.
