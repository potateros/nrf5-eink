"""BLE client for EPD-nRF5 firmware (service 62750001-...)."""
import asyncio
import struct
import time

from bleak import BleakClient, BleakScanner

from . import rle

SVC = "62750001-d828-918d-fb46-b6c11c675aec"
CHAR = "62750002-d828-918d-fb46-b6c11c675aec"
VER = "62750003-d828-918d-fb46-b6c11c675aec"

CMD_INIT, CMD_CLEAR, CMD_REFRESH, CMD_SLEEP = 0x01, 0x02, 0x05, 0x06
CMD_SET_TIME, CMD_SET_WEEK_START, CMD_WRITE_IMAGE = 0x20, 0x21, 0x30
CMD_SET_CONFIG = 0x90
WIPE_SECONDS = 25
REFRESH_SECONDS = 30
CFG_DISPLAY_MODE = 11  # byte offset of display_mode in epd_config_t

MODE_PICTURE, MODE_CALENDAR, MODE_CLOCK = 0, 1, 2


class DeviceNotFound(RuntimeError):
    """The scan ended without seeing the tag: out of range, between its intermittent adverts, or
    already connected to another central (it stops advertising then)."""


def _tz_hours() -> int:
    return (-time.altzone if time.localtime().tm_isdst else -time.timezone) // 3600


class EPD:
    def __init__(self, name_prefix: str = "NRF_EPD", address: str | None = None, invert: bool = False):
        # Polarity matches upstream (1 = white). An apparent inversion seen early on was a refresh
        # frozen in its negative phase by disconnecting too soon (see REFRESH_SECONDS).
        self.name_prefix, self.address, self.invert = name_prefix, address, invert
        self.client: BleakClient | None = None
        self.messages: list[bytes] = []
        self.mtu = 20
        self.rle = False
        self.stage = "scan"      # how far a push got: scan, connect, upload, refresh, config (for failure logs)
        self.rssi: int | None = None  # signal strength of the advert we connected from, dBm

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        if self.client:
            await self.client.disconnect()

    async def connect(self, timeout: float = 45):
        self.stage = "scan"

        def match(d, a):
            hit = bool((self.address and d.address == self.address) or (a.local_name or "").startswith(self.name_prefix))
            if hit:
                self.rssi = a.rssi
            return hit

        dev = await BleakScanner.find_device_by_filter(match, timeout=timeout)
        if not dev:
            raise DeviceNotFound(f"no {self.name_prefix} advert in a {timeout:.0f} s scan")
        self.stage = "connect"
        self.client = BleakClient(dev)
        await self.client.connect()
        await self.client.start_notify(CHAR, lambda _, b: self.messages.append(bytes(b)))
        await self._write(bytes([CMD_INIT]))
        await asyncio.sleep(1.0)
        for m in self.messages:
            text = m.decode(errors="replace")
            if text.startswith("mtu="):
                self.mtu = int(text[4:].split()[0])
                self.rle = "rle=1" in text

    @property
    def config(self) -> bytes | None:
        return self.messages[0] if self.messages else None

    @property
    def info(self) -> dict[str, str]:
        out = {}
        for m in self.messages[1:]:
            for tok in m.decode(errors="replace").split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    out[k] = v
        return out

    async def version(self) -> str:
        raw = await self.client.read_gatt_char(VER)
        return raw.rstrip(b"\0").decode(errors="replace") if len(raw) > 1 else hex(raw[0])

    async def _write(self, payload: bytes, response: bool = True):
        await self.client.write_gatt_char(CHAR, payload, response=response)

    async def _write_plane(self, data: bytes, red: bool, ack_every: int = 8):
        size = self.mtu - 2
        parts = rle.chunks(data, size) if self.rle else None
        use_rle = parts is not None and sum(map(len, parts)) < len(data)
        if not use_rle:
            parts = [data[i : i + size] for i in range(0, len(data), size)]
        for i, part in enumerate(parts):
            flags = (0x01 if red else 0) | (0x02 if i == 0 else 0) | (0x04 if use_rle else 0)
            last = i == len(parts) - 1
            await self._write(bytes([CMD_WRITE_IMAGE, flags]) + part, response=last or i % ack_every == ack_every - 1)

    async def show(self, black: bytes, red: bytes | None = None, wipe: bool = False):
        """Push packed planes (1 bit/px, MSB first, 1=white for black plane, 0=red for red plane) and refresh."""
        if wipe:
            # CLEAR is the only reliable wipe (a built-in calendar redraw leaves a mess). It blocks the
            # firmware for 20+ s, during which writes are acked by the BLE stack but never applied,
            # so wait until the app itself answers again instead of trusting a fixed delay.
            self.stage = "wipe"
            await self.clear()
            await asyncio.sleep(WIPE_SECONDS)  # don't send INIT earlier: it resets the panel mid-refresh
            await self.wait_ready()
        else:
            await self.wait_ready()
        self.stage = "upload"
        if self.invert:
            black = bytes(b ^ 0xFF for b in black)
        await self._write_plane(black, red=False)
        # Always rewrite the red RAM too (0xFF = no red): this is a B/W/R panel, and a stale red RAM
        # shows through as a red overlay unless CLEAR wiped it first.
        await self._write_plane(red if red is not None else b"\xff" * len(black), red=True)
        self.stage = "refresh"
        await self._write(bytes([CMD_REFRESH]))
        # Disconnecting powers the panel down; doing that mid-refresh freezes it on a black phase.
        await asyncio.sleep(REFRESH_SECONDS)

    async def arm_fallback(self, mode: int = MODE_CALENDAR):
        """Flip the stored display mode without redrawing.

        The picture stays on screen, but the firmware's own timer will redraw its built-in
        view at the next trigger (calendar: local midnight). Every push re-arms this, so the
        built-in date view only appears if pushes stop.
        """
        self.stage = "config"
        cfg = bytearray(self.config or b"")
        if len(cfg) <= CFG_DISPLAY_MODE:
            raise RuntimeError(f"unexpected config {cfg.hex()}")
        cfg[CFG_DISPLAY_MODE] = mode
        await self._write(bytes([CMD_SET_CONFIG]) + bytes(cfg))

    async def wait_ready(self, timeout: float = 90) -> float:
        """Send INIT until the firmware replies with `mtu=` (proves it's idle and initialised). Returns seconds waited."""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            seen = len(self.messages)
            await self._write(bytes([CMD_INIT]))
            for _ in range(20):
                await asyncio.sleep(0.25)
                if any(m.startswith(b"mtu=") for m in self.messages[seen:]):
                    return time.monotonic() - start
        raise TimeoutError("firmware did not answer INIT")

    def clock_drift(self) -> float | None:
        """Device clock minus host clock, in seconds (device reports local time in `t=`)."""
        if "t" not in self.info:
            return None
        return int(self.info["t"]) - (time.time() + _tz_hours() * 3600)

    async def set_time(self, mode: int = MODE_CALENDAR, ts: float | None = None):
        ts = int(ts if ts is not None else time.time())
        await self._write(bytes([CMD_SET_TIME]) + struct.pack(">I", ts) + struct.pack("bB", _tz_hours(), mode))

    async def clear(self):
        await self._write(bytes([CMD_CLEAR]))
