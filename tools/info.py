"""Connect and print everything the device reports: version, decoded config, notifications, clock drift.

  uv run python tools/info.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from epd.device import EPD  # noqa: E402

FIELDS = ["mosi", "sclk", "cs", "dc", "rst", "busy", "bs", "model", "wakeup", "led", "en", "display_mode",
          "week_start", "byte13(?)"]
MODES = {0: "picture", 1: "calendar", 2: "clock"}


async def main():
    async with EPD() as e:
        print("version :", await e.version())
        print("mtu/rle :", e.mtu, e.rle)
        cfg = e.config or b""
        print("config  :", cfg.hex(" "))
        for name, b in zip(FIELDS, cfg):
            extra = f" ({MODES.get(b, '?')})" if name == "display_mode" else ""
            print(f"  {name:13} 0x{b:02x}{extra}")
        print("info    :", e.info)
        drift = e.clock_drift()
        print("drift   :", "n/a" if drift is None else f"{drift:+.0f} s (includes ~1-4 s BLE latency)")


asyncio.run(main())
