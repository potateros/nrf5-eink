"""Set the device clock to host time, aligned to a whole second (EPD.set_time truncates time.time(),
so it can start up to 1 s behind). SET_TIME forces a built-in calendar redraw; wait for it.

  uv run python tools/experiments/clock_sync.py
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from epd import device  # noqa: E402
from epd.device import EPD, MODE_CALENDAR  # noqa: E402


async def main():
    async with EPD() as e:
        await asyncio.sleep(1 - time.time() % 1)  # wait for the next whole second
        sec = round(time.time())
        await e.set_time(MODE_CALENDAR, ts=sec)
        print("SET_TIME", sec, "sent at", f"{time.time():.3f}", flush=True)
        await asyncio.sleep(device.WIPE_SECONDS + 5)


asyncio.run(main())
