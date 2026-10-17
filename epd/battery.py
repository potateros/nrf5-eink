"""Battery estimate from the `bat=` reading the device reports on connect."""

LOW_PCT = 30  # below the knee of the firmware curve: charge soon


def battery_pct(mv: int) -> int:
    """Estimated charge %, using the firmware's own curve (upstream GUI.c `batt_cal`), so the
    dashboards agree with the battery glyph on its built-in calendar. It's an estimate: `bat=` is
    the ~3.0 V rail, which stays flat for most of the cell's life (2.91-2.93 V, i.e. ~65-75 %
    here) and only drops near the end. A falling number means charge soon."""
    adc = mv * 2047 // 3600
    for hi, lo, top, span in ((1705, 1584, 28, 72), (1584, 1360, 4, 24), (1360, 1136, 0, 4)):
        if adc > hi:
            return 100 if hi == 1705 else top + span
        if adc > lo:
            return top + (adc - lo) * span // (hi - lo)
    return 0


def battery_level(mv: int) -> tuple[float, str]:
    """(fill 0..1, label) for a battery glyph: label is "~69%", or "~25% LOW" below LOW_PCT."""
    pct = battery_pct(mv)
    return pct / 100, f"~{pct}%" + (" LOW" if pct < LOW_PCT else "")
