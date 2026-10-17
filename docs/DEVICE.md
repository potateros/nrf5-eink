# NRF_EPD_5E5D — device notes

Living document. Everything we learn about this display goes here.

Status tags:
- **[verified]** observed on this exact unit
- **[source]** read in firmware source of a related project, not yet confirmed here
- **[online]** reported by someone else on similar hardware
- **[open]** unknown / to investigate

Last updated: 2026-10-17 (slot/carousel opcodes found in the myetoys web tool, §2.0b). Before that, 2026-10-16: red verified, controller identified, seller listing + upstream v1.10 source/web tool review. Capability overview: [CAPABILITIES.md](CAPABILITIES.md)

---

## 1. Hardware

| Item | Value | Status |
| --- | --- | --- |
| MCU | Nordic nRF52811 (firmware reports `nrf52811`) | [verified] |
| Panel | 4.2", 400×300 | [verified] (full-frame 400×300 image fills screen) |
| Colours | Black / white / **red** — red is drawn by the firmware's built-in calendar | [verified] |
| Panel controller | **SSD16xx command set (SSD1619-compatible).** Raw `0x4E`/`0x4F` + `0x26` (red RAM) via SEND_CMD/DATA drew a red box after REFRESH (`tools/experiments/raw_ssd1619_probe.py`). Model id `0x16` is not in upstream (which stops at `0x11`); it's this variant's own id | [verified] 2026-10-16 |
| Battery | 1100 mAh Li-ion (per owner) | [verified by owner] |
| Battery telemetry | Firmware reports `bat=<mV>`; reads 2907–2932 mV. Almost certainly the **regulated VDD rail**, not the cell (a Li-ion at 2.9 V would be cut off). The built-in calendar shows it as `2.9V` + a glyph filled by upstream's `batt_cal` curve (coin-cell shaped: ≥ 2999 mV = 100 %, 2785 mV = 28 %, 2392 mV = 4 %), ≈ 68 % at 2907 mV. Our dashboards use the same curve. Upstream's `EPD_ReadVoltage` samples the nRF **VDD pin** with the SAADC (`PSELP = VDD`, gain 1/6, internal 0.6 V ref, 10-bit), so it is the supply after the regulator, by design | [verified] reading + calendar glyph / [source] VDD |
| Temperature sensor | The panel controller's built-in sensor (SSD16xx: update `0xB1`, then read reg `0x1B`). Upstream reads it at every built-in redraw and prints it only in clock mode, as `19℃[5E5D]` (°C + last 4 chars of the BLE name). The seller's photo shows exactly that. Not reported over BLE | [source] / [online] photo |
| Debug | No SWD probe attached; all access over BLE | — |

## 2. Firmware

A **non-public variant** of [tsl0922/EPD-nRF5](https://github.com/tsl0922/EPD-nRF5). It matches neither upstream nor any fork we checked (incl. [YCD12/EPD-nRF5_DYC](https://github.com/YCD12/EPD-nRF5_DYC)).

| Item | Value | Status |
| --- | --- | --- |
| Version characteristic (`62750003`) | String `v1.10-nrf52811\0` (upstream returns one byte, e.g. `0x1a`; DYC `0x20`) | [verified] |
| Base version | Upstream tag **v1.10** (released 2026-08-08, `APP_VERSION 0x1a`) is the same version number, so the variant is most likely built on upstream v1.10. Upstream HEAD (2026-09-08) is 4 small commits past it | [source] |
| BLE name | `NRF_EPD_5E5D` (upstream: `NRF_EPD_` + last 2 bytes of MAC) | [verified] |
| Image transfer RLE | Supported (`rle=1`) | [verified] |
| MTU | 247 negotiated, firmware reports `mtu=244` → 242 bytes image data per packet | [verified] |
| OTA | Nordic **Secure DFU** service `FE59` (buttonless) present. Upstream publishes its signing key (`tools/priv.pem`) and bootloader hex, but we don't know whether the vendor's bootloader trusts that key, and flashing upstream would lose the variant's extras (§2.0) anyway → do **not** attempt | [verified] presence / [source] key |
| Image "slots" | Notifies `slots=15 <mask> 255`. Mask `0` in the first session, `32767` (`0x7FFF`, all 15 bits) on the evening of 2026-10-16. The myetoys web tool (§2.0b) reads it as `slots=<count> <used bitmask> <current slot>` (bit set = used) and drives it with `0x31`–`0x33` (§4). 15 raw frames (60 KB each with red) wouldn't fit in 192 KB flash, so storage is compressed or external | [verified] values / [source] meaning |
| `sid=` | 64-hex-char ID (`F9196A6B…BA15`). The myetoys web tool sends it as the `X-Machine-ID` header to a **paid remote-template renderer** (`POST https://25565.shop/render`) when a template is rendered remotely; a 401 means "paid feature: if your device is registered, ask the seller for an OTA package". So it's a licence/device ID. Keep it out of anything public; we never call that service | [source] 2026-10-17 |

### 2.0 Seller listing (Pinduoduo, "upgraded version")

The owner's unit is the listing's **升级版 (upgraded version)**, which explains the non-public firmware. The listing credits "tls0922" (sic, tsl0922) for the open source. Screenshots read 2026-10-16.

| Claim | Status |
| --- | --- |
| 4.2" **black/white/red** three-colour panel; no greyscale is offered anywhere in the listing | [online] |
| 1100 mAh Li-ion, Type-C. Use a plain 5 V / 1–2 A charger, avoid fast chargers. LED beside the port (right side): red = charging, blue = full | [online] |
| Standby "about 2 months" in calendar mode | [online] |
| Physical power switch on the right side: down = on, up = off. After a power cycle the device must be set up again (clock reset, §6.1) | [online] |
| Calendar/time not updating or a garbled screen means low voltage: charge it | [online] |
| Warning: the three-colour screen isn't recommended as a clock, with partial or full refresh — frequent refreshes risk burn-in (烧屏) | [online] |
| Configured through a WeChat mini-program or a web page (one-click time sync); some Xiaomi/HarmonyOS/iOS phones can't find it in the mini-program and should use the web page. The firmware's own sync prompt points at upstream's tool (§2.0a), so the "web page" is most likely that | [online] |
| Back has 4 magnets; hand-made 3D-printed case | [online] |
| Product photo of clock mode shows date, lunar date, a `3.3V` battery reading and a temperature (`19℃`) | [online] |

Standard vs upgraded firmware (feature table):

| Feature | Standard | Upgraded (ours) |
| --- | --- | --- |
| Calendar | yes | yes |
| Doodle / drawing board | yes | yes |
| Clock with **partial refresh** | no | yes ("core upgrade") |
| Countdown | no | yes ("core upgrade") |
| Picture upload | 1 image | **6-image carousel** ("core upgrade") |
| Templates | no | to-do list, timetable, business card, QR code, … |

So the variant has a partial-refresh clock mode (contradicts §6's upstream-based "full refresh every minute" for this unit) and stored images that rotate, likely what the `slots=` notification is about (§2, open question 2). The opcodes for these are still unknown.

### 2.0a Upstream web tool (tsl0922.github.io/EPD-nRF5)

The vendor's firmware still shows upstream's **"SYNC TIME!"** box (§6), which sends buyers to upstream's web tool. Reviewed 2026-10-16: the live site is byte-identical to `html/` at upstream HEAD.

| Behaviour | Status |
| --- | --- |
| Web Bluetooth: desktop/Android Chrome or Edge, **Bluefy** on iOS. Connects, reads the version characteristic's **first byte**, then sends `INIT` | [source] |
| Version byte < `0x16` → warns "firmware too old" and offers the legacy tool at `/EPD-nRF5/v1.5`. Our string starts with `v` (`0x76`), so it's treated as current | [source] |
| Notifications: config bytes (fills the pin and driver fields), `mtu=` (+ `rle=1` turns on RLE), `t=` (logs device vs local time). `slots=` and `sid=` are just logged, so the variant's extras aren't driven from here | [source] |
| **日历模式 / 时钟模式** (calendar / clock) buttons = `SET_TIME` with mode 1 / 2 and the browser's timezone. That's the "sync time" fix | [source] |
| Clock mode asks for confirmation first: "clock mode currently uses full refreshes; it's mostly used to **repair ghosting on aged screens**; not recommended long-term" | [source] |
| Also: clear screen, raw command box (hex, first byte = opcode), image upload with crop and dithering (Floyd-Steinberg / Atkinson / Bayer; BW, BWR, BWRY, 6-colour), and a paint/text canvas (the listing's "doodle") | [source] |
| **Risk for this unit:** the "设置驱动" (set driver) button sends `SET_PINS` + `INIT <model>`. The driver list stops at `0x11`, so any choice overwrites our model `0x16`. Don't press it | [source] |

### 2.0b myetoys web tool (www.myetoys.com/EPD-nRF5/) — the variant's own client

myetoys.com (墨韵时光) publishes guides for TSL0922-firmware calendars, sells them (Goofish listing), and hosts **its own build of the web tool** that drives the variant's extras. Downloaded and decoded 2026-10-17 (obfuscated Vite bundle `cache/index-BUjqGby-.js`, last-modified 2026-01-30; decoded copy only in the session scratchpad, never run against the device). Its guide also mentions a "群友开发的小程序" (a mini-program written by a community member) reached by QR code, with no support from the author. It is probably the WeChat client the seller listing means.

| Finding | Status |
| --- | --- |
| Command enum: upstream's plus `SET_SLOT: 0x31`, `FREE_SLOT: 0x32`, `SET_SLIDE: 0x33` (§4). No `0x93` | [source] |
| A slot panel ("选择图片槽位") appears only when `slots=` reports a count > 0: one button per slot (● used / ○ empty), **显示槽位** (show), **删除槽位** (delete, "irreversible"), and **启动轮播** (start carousel) with an interval in minutes (default 60) | [source] |
| Upload with slots: `SET_SLOT [0, n]`, then the usual `INIT` → image chunks → `REFRESH`. So the target slot survives `INIT`, and the uploaded frame is stored in slot n (it warns before overwriting a used slot) | [source] |
| Show: `SET_SLOT [1, n]`, then `SET_TIME` with mode 0 (picture) | [source] |
| Carousel: `SET_SLIDE [interval_hi, interval_lo]` (u16 big-endian minutes). "Press another mode button under device control to leave carousel mode", so any `SET_TIME` mode change ends it | [source] |
| It treats config byte 13 as the current slot, then overwrites that with the `slots=` third field | [source] |
| **Slot test on this unit** (2026-10-17, `tools/experiments/slot_test.py`, webcam frames in `.cache/slot_test/`): see §2.0c | [verified] |
| New notification `clock_enable=0|1`: on 0 the clock button becomes "刷新模式" (refresh mode). Our unit never sends it | [source] / [verified] absent |
| Templates (to-do, timetable, card, …) are canvas layouts rendered in the browser, or remotely via the paid service (`sid`, §2), then uploaded as an ordinary image. They aren't firmware features | [source] |
| Driver list stops at `0x0c`; no model `0x16`, so its "set driver" button is as dangerous as upstream's | [source] |
| Image chunks use flag `0x0F` (black) / `0x00` (red), with `0xF0` OR'd in after the first chunk, and no RLE. That's not our modern bit layout (§5.1), yet both work, so the variant accepts either | [source] |

### 2.0c Slot test results (2026-10-17, owner-approved)

| Finding | Status |
| --- | --- |
| **Show works.** `0x31 [1, n]` + `SET_TIME` mode 0 redraws slot n (full refresh). Afterwards byte 13 = n, `slots=` third field = n, byte 11 = 0 (picture) | [verified] |
| **Store works, full frame, with RLE.** `0x31 [0, n]` then our normal `EPD.show()` (INIT, RLE black + red planes, REFRESH) stored a 400×300 marker frame in slot n; showing it later reproduced it top to bottom, red included. Storing also displays it | [verified] |
| **Every plain push is saved into the current slot (byte 13).** After the test left byte 13 = 7, a normal push, then a different slot, then showing 7 again gave back that push. Byte 13 sat at 4 since the first day, so every scheduled push rewrote slot 4. `slots=` third field is `255` after boot until a slot is shown, while byte 13 (persisted) keeps the target. So the 0 → `0x7FFF` mask was our first day's pushes landing in whatever slot was current | [verified] |
| **The first day's slots were half frames**: only the top ~145 of 300 rows were intact, with noise below (and red bleeding through in some). Our early scripts disconnected ~2 s after REFRESH. A likely cause: the flash write runs after REFRESH and was cut short | [verified] observation / [open] cause |
| **Carousel works.** `0x33 [0, 1]` rotated through the stored slots about once a minute with no Mac connected. Byte 11 stayed `0`, so the carousel isn't stored there; byte 13 didn't change either | [verified] |
| **A normal push ends the carousel.** After a push (INIT, upload, REFRESH, `SET_CONFIG` calendar) the pushed frame stayed for 2.5 min of watching. So the scheduled pipeline is safe; a carousel only lasts until the next push | [verified] |
| **Flash wear (estimate).** With every push rewriting one slot, that slot takes ~33 writes a day. nRF52 flash is rated for 10 000 erase cycles, roughly 300 days for one page, *if* each push erases the same page. We don't know how the firmware lays the slots out (15 full frames don't fit in 192 KB raw, so they're compressed or wear-levelled). Cheap mitigation if needed: send `0x31 [0, k]` before each push with k rotating through the 15 slots | [estimate] / [open] |
| Untested: whether the carousel survives the midnight redraw or a power cycle; `0x32` FREE_SLOT | [open] |

### 2.1 Notifications sent after `INIT` (0x01)

Observed in order:

1. Raw config bytes (14 bytes, see §3) — sent when notifications are enabled
2. `slots=15 <mask> 255` (mask seen as `0` and `32767`)
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
| 13 | Not in upstream: **current slot**, where the next upload is stored (§2.0c) | was `0xFF`, then `0x04` from the first day until the slot test on 2026-10-17 | [verified] |

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
| `0x31` | SET_SLOT | `u8 op`, `u8 slot` | Variant (§2.0b): op 0 = store the next upload in `slot`, op 1 = show `slot` (followed by `SET_TIME` mode 0). Both set config byte 13 to `slot` (seen with show, and with op 0 followed by an upload; op 0 alone is [open], and the web tool relies on it to re-point the target at scratch slot 14). (In the DYC fork `0x31`–`0x33` are a CRC'd block transfer instead.) | [verified] 2026-10-17 |
| `0x32` | FREE_SLOT | `u8 slot` | Variant: delete the stored image. Irreversible | [source] — needs owner OK |
| `0x33` | SET_SLIDE | `u16 BE minutes` | Variant: start the carousel through used slots. A normal push ends it; the tool says any `SET_TIME` mode change does too | [verified] 2026-10-17 |
| `0x34–0x4F` | — | — | `0x31`–`0x4F` sent with no arguments do nothing visible (no reply, no state change, no redraw; probed twice 2026-10-16). That fits `0x31`–`0x33` returning early on a short write | [verified] no-arg |
| `0x93` | GET_INFO | — | Only in an unmerged upstream PR (#20, 2026-10-06, for an nRF52811 + SSD1619 4.2" BWR tag): replies `v=<mV> m=<mode>`. Not in upstream or (as far as we know) the variant | [online] / [open] on this unit |
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
| **Red works.** Modern red plane (bit 0 = 1), 0 = red, held 60 s: solid red, stripes, 1 px lines and 16/21 px text all sharp, no ghosting without CLEAR (webcam, `tools/experiments/red_card.py`). The earlier "red overwrites black" was the cut-short refresh | [verified] 2026-10-16 |
| **REFRESH is asynchronous on this variant.** A notification re-enable (the firmware answers with its config) was answered 0.2 s after REFRESH; upstream would block until BUSY clears. The hold is still needed: disconnect powers the panel down | [verified] 2026-10-16 |
| Refresh timeline (webcam, 1 fps, from REFRESH): flash/inversion 0–8 s, black/white settled ~14 s, red saturated ~18 s, final ~22 s. 30 s hold = ~8 s margin | [verified] 2026-10-16 |
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

### 5.3 Red on uploads — resolved

**Red works** with the modern red plane and the 30 s hold (§5.1). The raw SSD1619 probe also works when held (2026-10-16 rerun: red box drawn via raw `0x26`). The table below is the original, cut-short history. [verified]

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
| Calendar (1) | Firmware-rendered month calendar (Chinese lunar dates, solar terms, holidays); uses red. Top right: `2.9V` + battery glyph over the device name. Redraws at **local midnight** (`timestamp % 86400 == 0`): a pushed picture with calendar armed via SET_CONFIG was replaced at device 00:00:00 exactly (clock set to 23:58, webcam) | [verified] 2026-10-16 |
| Clock (2) | Firmware-rendered clock + date. Upstream: **full refresh every minute** (flashes, drains battery); its web tool warns before enabling it (§2.0a). The seller says the upgraded variant does this with **partial refresh** (§2.0), but also warns against long-term clock use (burn-in). It can't show an uploaded picture: the minute timer redraws the built-in layout | [source] / [online] variant |
| Clock layout | Top: date, weekday, lunar date; battery glyph and `NN℃[5E5D]` on the right. Middle: big HH:MM. Bottom: stem-branch year with the zodiac animal in red (`乙巳蛇年`), ISO week (`44周`), and the next solar term with a countdown (`离立冬 还有6天`). The seller's 2025-11-01 photo matches upstream's layout exactly | [source] / [online] photo |
| Time-sync hint | In calendar or clock mode, while the RTC is in **January 2025** (power-on default, never set), the firmware draws a centred box: red **"SYNC TIME!"** over `https://tsl0922.github.io/EPD-nRF5`. That's the popup in buyers' photos. On our unit it would mean the clock was lost (power switch cycled or battery flat) | [source] / [online] |
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
| `SET_TIME` doesn't reset the 1 s timer's phase, and `EPD.set_time` sends `int(time.time())` (truncates up to 1 s), so a sync is good to about ±1 s. Measured −0.74 s right after a whole-second-aligned sync (`tools/experiments/clock_sync.py`) | [verified] 2026-10-16 |
| Precise offset: `tools/experiments/clock_offset.py` polls INIT every 0.1 s and catches the `t=` tick (±0.15 s) | [verified] |
| Upstream configures the SoftDevice LF clock as the **internal RC** (`NRF_CLOCK_LF_SRC_RC`, recalibrated every 16 × 0.25 s), which explains the drift below | [source] |
| **Drift: the clock runs fast, ~+120 ppm (±60)**, i.e. ~5–15 s/day: −0.74 s at 22:03:22 → −0.31 s at 23:02:24 (2026-10-16, no SET_TIME between). Too fast for a 32 kHz crystal (±20 ppm), so the low-frequency clock is the internal RC oscillator. Our push resyncs when off by > 30 s, so expect a SET_TIME (and its built-in redraw) every few days. A full-day rerun would tighten the number | [verified] 2026-10-16 |
| Measured offset −4 s on two pushes ~15 min apart → the −4 s is mostly measurement latency (`t=` is sent at INIT, host time is read ~1–4 s later); real drift is small so far | [verified] preliminary |

## 7. How we use it (this repo)

See the [README](../README.md) for the software. Pushes are scheduled by homelab-hq (every 30 min 07:00–23:00, re-push at 00:01); see README "Scheduling". `uv run python tools/info.py` dumps everything the device reports (version, decoded config, battery, clock drift).


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
| GATT: `62750001` (`62750002` write/write-no-rsp/notify, CCCD h=14; `62750003` read) and `FE59` Buttonless DFU (`8ec90003` indicate/write). Nothing else (no Device Information or Battery service). `tools/experiments/gatt_dump.py` | [verified] 2026-10-16 |
| A Logitech webcam aimed at the panel makes visual checks possible without the owner | [verified] 2026-10-16 |
| Only one central at a time: close the web tool before running scripts. A manual push during a scheduled one fails, so hold the hq job first | [online] / [verified] |
| Under launchd, CoreBluetooth permission belongs to the runner (`bun`), not the terminal: `BleakBluetoothNotAvailableError: Bluetooth access is denied` until `bun` is allowed in Privacy & Security → Bluetooth | [verified] 2026-10-16 |

## 9. Open questions

1. ~~What is model `0x16`? Does red work?~~ Resolved 2026-10-16: SSD16xx-compatible controller, red works (§5.1).
2. ~~Slots~~: resolved 2026-10-17 (§2.0b, §2.0c). Store, show and carousel verified; every plain push lands in the current slot. Still open: flash layout and wear, the carousel across midnight or a power cycle, and FREE_SLOT.
3. ~~What is `sid`, and what is config byte 13?~~ `sid` = licence ID for the paid template renderer; byte 13 = current slot per the myetoys tool (§2.0b) [source].
4. ~~Does calendar mode switch over at midnight?~~ Yes, verified 2026-10-16 (§6).
5. Config byte 13 (`0x04`): upstream's config is 13 bytes, so it's variant-only. Unchanged across SET_TIME, SET_CONFIG, CLEAR-less pushes and REFRESH on 2026-10-16.
6. Does the variant answer `0x93` (GET_INFO, PR #20) or expose the panel temperature? Low priority: `INIT` already gives `bat=`.

## Sources

- [tsl0922/EPD-nRF5](https://github.com/tsl0922/EPD-nRF5) — upstream firmware + web tool (protocol, RLE, modes); live tool at [tsl0922.github.io/EPD-nRF5](https://tsl0922.github.io/EPD-nRF5)
- [tsl0922/EPD-nRF5#20](https://github.com/tsl0922/EPD-nRF5/pull/20) — unmerged: `0x93` GET_INFO, GCC Makefile, Windows host for a 4.2" nRF52811 BWR tag
- Pinduoduo seller listing (owner's screenshots, 2026-10-16) — §2.0
- [myetoys.com web tool](https://www.myetoys.com/EPD-nRF5/) and [TSL0922 firmware guide](https://www.myetoys.com/tsl0922/34.html) — the variant's slot/carousel client, §2.0b
- [YCD12/EPD-nRF5_DYC](https://github.com/YCD12/EPD-nRF5_DYC) — fork with legacy flags + CRC block transfer
- [askfanxiaojun/epd-ai-quota-display](https://github.com/askfanxiaojun/epd-ai-quota-display) — macOS + BLE pusher for a 400×300 BWR nRF52811 tag; legacy-flag protocol notes
- [jam422470459/EPD-nRF52-hema213](https://github.com/jam422470459/EPD-nRF52-hema213), [jyh9521/EPD-nRF5-JP](https://github.com/jyh9521/EPD-nRF5-JP) — other nRF52811 forks
