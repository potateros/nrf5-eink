# WIP layouts (2026-10-17)

Mockups only: not registered in `epd.cli`, never pushed. They reuse the live data and helpers (`epd.events`, `screens.at_a_glance`, `screens.common`), so they render today's real calendar, reminders and weather.

```sh
uv run python wip/landscape.py   # c1-c3, r1-r2 -> wip/images/
uv run python wip/portrait.py    # p1-p4 + portrait_sheet.png -> wip/images/
```

All keep the shared header with the battery top-right, Workato rows red, reminders with a hollow circle and red time/date, Sundays and holidays red, "…" truncation.

## Full calendar (landscape)

| | |
| --- | --- |
| **c1, week columns**: 7 day columns from today, time + 2-line title per event. Shows the week's shape, but ~55 px columns cut titles to 2-3 words; overdue reminders swamp Today. | ![c1](images/c1_week_columns.png) |
| **c2, two-column agenda** (pick): the at-a-glance agenda across the full width, flowing into a second column; ~12 days, titles to ~15 characters. | ![c2](images/c2_two_column_agenda.png) |
| **c3, four-week grid**: rolling 4 weeks from this Monday ("1 Nov" marks the month change). The calendar export starts today, so a calendar-month view would be half empty. Cells fit ~5 characters: a busy-days map more than a list. | ![c3](images/c3_four_week_grid.png) |

## Reminders only (landscape)

| | |
| --- | --- |
| **r1, Due + Tasks \| Shopping** (pick): everything dated (overdue dates red, "7 overdue" in the heading), then Tasks; Shopping on the right. | ![r1](images/r1_due_tasks_shopping.png) |
| **r2, overdue strip + three lists**: one red overdue line, then Tasks / Inbox / Shopping side by side in 12 px, titles wrapping to 2 lines. More lists, smaller text. | ![r2](images/r2_three_lists.png) |

## Portrait (300×400, rotated 90° for the panel)

![portrait sheet](images/portrait_sheet.png)

- **p1 agenda**: weather strip + full-width 14-day agenda; titles almost always fit.
- **p2 at-a-glance**: big date + weather, roomy month grid (40 px columns), agenda; overdue reminders fill the agenda.
- **p3 reminders**: Due, Tasks, Shopping stacked full width; titles show in full.
- **p4 weather**: now block, 2-hourly rows (time, icon, temp, rain bar, %), Today/Tmrw. Cleanest of the four.

Portrait caveats: the firmware's own screens (midnight calendar fallback, SYNC TIME prompt) stay landscape and would appear sideways if pushes stop; the panel must sit or hang on its side; each layout needs its own portrait design. Implementation would be a `config.toml` orientation flag that rotates the frame before `to_planes`.

## Open questions for the owner

- Promote c2 and/or r1 to real layouts (e.g. `week`, `todo`)? Which reminder lists (`config.toml`)?
- Go portrait? If so, p4 weather + p3 reminders are the strongest pair.
- Cap overdue reminders (e.g. two shown + "+5 overdue") everywhere they swamp Today?
