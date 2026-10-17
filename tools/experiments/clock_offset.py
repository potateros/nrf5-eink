"""Read-only: measure the device clock offset to ~0.1 s, plus the raw config and slots line.

Polls INIT every 0.1 s and catches the moment `t=` ticks over; at that instant the device is at exactly
t.000, so offset = t - host local time. Much tighter than one INIT round trip (1-4 s of latency).

  uv run python tools/experiments/clock_offset.py
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from epd.device import EPD, _tz_hours  # noqa: E402


def t_values(msgs):
    return [int(m.split()[0][2:]) for m in (x.decode(errors="replace") for x in msgs) if m.startswith("t=")]


async def main():
    async with EPD() as e:
        print("config:", (e.config or b"").hex(" "))
        print("raw   :", [m.decode(errors="replace") for m in e.messages[1:] if m.startswith(b"slots")])
        offsets, last = [], None
        for _ in range(60):
            seen = len(e.messages)
            sent = time.time()
            await e._write(bytes([0x01]))
            await asyncio.sleep(0.1)
            ts = t_values(e.messages[seen:])
            if ts:
                if last is not None and ts[-1] == last + 1:
                    offsets.append(ts[-1] - (sent + _tz_hours() * 3600))  # device ticked during this poll
                last = ts[-1]
        if offsets:
            print(f"offset device-host: {sum(offsets) / len(offsets):+.2f} s (n={len(offsets)}, "
                  f"range {min(offsets):+.2f}..{max(offsets):+.2f}) at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print("no tick caught")


asyncio.run(main())
