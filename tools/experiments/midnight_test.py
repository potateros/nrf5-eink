"""Does calendar mode take over from a pushed picture at local midnight? (2026-10-16)

1. SET_TIME to 23:58:00 local today (mode calendar: forces a built-in redraw; wait for it).
2. Push a picture labelled MIDNIGHT TEST (REFRESH sets mode = picture), hold 30 s.
3. SET_CONFIG display_mode = calendar (our dead-man arming), disconnect.
4. Watch the camera: at device 00:00:00 the calendar for the next day should replace the picture.
Restore afterwards with a whole-second-aligned SET_TIME (tools/experiments/clock_sync.py).

  uv run python tools/experiments/midnight_test.py
"""
import asyncio
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image, ImageDraw  # noqa: E402

from epd import device  # noqa: E402
from epd.device import EPD, MODE_CALENDAR  # noqa: E402
from epd.image import to_planes  # noqa: E402
from layouts.common import RED, bold, medium  # noqa: E402

img = Image.new("RGB", (400, 300), "white")
d = ImageDraw.Draw(img)
d.fontmode = "1"
d.text((20, 40), "MIDNIGHT TEST", font=bold(40), fill="black")
d.text((20, 110), "picture pushed at device 23:58", font=medium(16), fill="black")
d.text((20, 140), "calendar armed via SET_CONFIG", font=medium(16), fill="black")
d.text((20, 190), "should flip at 00:00", font=bold(21), fill=RED)
black, red = to_planes(img, red=True, dither=False)


async def main():
    async with EPD() as e:
        tz = device._tz_hours()
        local_2358 = dt.datetime.combine(dt.date.today(), dt.time(23, 58))
        utc_ts = int(local_2358.timestamp())
        await e.set_time(MODE_CALENDAR, ts=utc_ts)
        print("SET_TIME -> device 23:58:00 at", time.strftime("%H:%M:%S"), "tz", tz, flush=True)
        await asyncio.sleep(device.WIPE_SECONDS + 5)  # built-in calendar redraw runs async
        await e.wait_ready()
        await e._write_plane(black, red=False)
        await e._write_plane(red, red=True)
        await e._write(bytes([device.CMD_REFRESH]))
        print("REFRESH at", time.strftime("%H:%M:%S"), flush=True)
        await asyncio.sleep(device.REFRESH_SECONDS)
        await e.arm_fallback(MODE_CALENDAR)
        await asyncio.sleep(1)
        seen = len(e.messages)
        await e._write(bytes([0x01]))
        await asyncio.sleep(1)
        print("after arming:", [m.decode(errors="replace") for m in e.messages[seen:]], flush=True)
        print("disconnect at", time.strftime("%H:%M:%S"), flush=True)


asyncio.run(main())
