"""Owner-approved probe (2026-10-16): send unused opcodes one at a time with no arguments and record
any reply. After each: INIT, check config + slots line unchanged. Stops at the first opcode that does
anything (a notification, a config/slots change, or a disconnect) so it can be examined alone.

Ranges: 0x31-0x3F and 0x40-0x4F only. Never 0x00/0x92/0x99/DFU.

  uv run python tools/experiments/opcode_probe.py [first_opcode_hex]
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from epd.device import EPD  # noqa: E402

OPS = list(range(0x31, 0x40)) + list(range(0x40, 0x50))
FORBIDDEN = {0x00, 0x92, 0x99}


def state(msgs):
    cfg = msgs[0].hex() if msgs else None
    slots = next((m.decode() for m in msgs if m.startswith(b"slots")), None)
    return cfg, slots


async def main(start: int):
    async with EPD() as e:
        base_cfg, base_slots = e.config.hex(), state(e.messages[1:])[1]
        print("baseline", base_cfg, base_slots, flush=True)
        for op in OPS:
            if op < start or op in FORBIDDEN:
                continue
            seen = len(e.messages)
            print(f"{time.strftime('%H:%M:%S')} send 0x{op:02x}", flush=True)
            await e._write(bytes([op]))
            await asyncio.sleep(2.0)
            replies = e.messages[seen:]
            if replies:
                print("   REPLY:", [r.hex(" ") + " | " + r.decode(errors="replace") for r in replies], flush=True)
                return
            seen = len(e.messages)
            await e._write(bytes([0x01]))
            await asyncio.sleep(1.0)
            after = e.messages[seen:]
            slots = next((m.decode() for m in after if m.startswith(b"slots")), None)
            if not any(m.startswith(b"mtu=") for m in after) or (slots and slots != base_slots):
                print("   CHANGE after INIT:", [m.decode(errors="replace") for m in after], flush=True)
                return
        print("no opcode replied", flush=True)


asyncio.run(main(int(sys.argv[1], 16) if len(sys.argv) > 1 else 0))
