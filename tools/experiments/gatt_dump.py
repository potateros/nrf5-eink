"""Read-only: list every GATT service/characteristic/descriptor, read what's readable, print raw notifications.

  uv run python tools/experiments/gatt_dump.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from epd.device import EPD  # noqa: E402


async def main():
    async with EPD() as e:
        c = e.client
        print("address:", c.address, "mtu:", c.mtu_size)
        for s in c.services:
            print(f"service {s.uuid} ({s.description})")
            for ch in s.characteristics:
                val = ""
                if "read" in ch.properties:
                    try:
                        raw = await c.read_gatt_char(ch)
                        val = f" = {raw.hex(' ')} {raw!r}"
                    except Exception as ex:  # noqa: BLE001
                        val = f" read error {ex}"
                print(f"  char {ch.uuid} h={ch.handle} {ch.properties} ({ch.description}){val}")
                for d in ch.descriptors:
                    try:
                        dv = (await c.read_gatt_descriptor(d.handle)).hex(" ")
                    except Exception as ex:  # noqa: BLE001
                        dv = f"err {ex}"
                    print(f"    desc {d.uuid} h={d.handle} = {dv}")
        print("raw notifications after INIT:")
        for m in e.messages:
            print("  ", m.hex(" "), "|", m.decode(errors="replace"))


asyncio.run(main())
