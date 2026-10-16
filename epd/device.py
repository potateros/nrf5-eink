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
CFG_DISPLAY_MODE = 11  # byte offset of display_mode in epd_config_t

MODE_PICTURE, MODE_CALENDAR, MODE_CLOCK = 0, 1, 2


def _tz_hours() -> int:
    return (-time.altzone if time.localtime().tm_isdst else -time.timezone) // 3600


class EPD:
    def __init__(self, name_prefix: str = "NRF_EPD", address: str | None = None, invert: bool = True):
        # Model 0x16 on the NRF_EPD_5E5D unit has inverted polarity vs upstream (0 = white).
        self.name_prefix, self.address, self.invert = name_prefix, address, invert
        self.client: BleakClient | None = None
        self.messages: list[bytes] = []
        self.mtu = 20
        self.rle = False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        if self.client:
            await self.client.disconnect()

    async def connect(self, timeout: float = 45):
        dev = await BleakScanner.find_device_by_filter(
            lambda d, a: (self.address and d.address == self.address)
            or (a.local_name or "").startswith(self.name_prefix),
            timeout=timeout,
        )
        if not dev:
            raise RuntimeError(f"no device matching {self.name_prefix!r}")
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
            # CLEAR is the only reliable wipe (a built-in calendar redraw leaves a mess), and the
            # panel needs ~20 s to finish; show() sends INIT again afterwards, which CLEAR requires.
            await self.clear()
            await asyncio.sleep(WIPE_SECONDS)
        await self._write(bytes([CMD_INIT]))
        if self.invert:
            black = bytes(b ^ 0xFF for b in black)
        await self._write_plane(black, red=False)
        if red is not None:
            await self._write_plane(red, red=True)
        await self._write(bytes([CMD_REFRESH]))

    async def arm_fallback(self, mode: int = MODE_CALENDAR):
        """Flip the stored display mode without redrawing.

        The picture stays on screen, but the firmware's own timer will redraw its built-in
        view at the next trigger (calendar: local midnight). Every push re-arms this, so the
        built-in date view only appears if pushes stop.
        """
        cfg = bytearray(self.config or b"")
        if len(cfg) <= CFG_DISPLAY_MODE:
            raise RuntimeError(f"unexpected config {cfg.hex()}")
        cfg[CFG_DISPLAY_MODE] = mode
        await self._write(bytes([CMD_SET_CONFIG]) + bytes(cfg))

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
