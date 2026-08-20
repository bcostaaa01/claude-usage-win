"""Shared color palette for the tray icon gauge and dashboard, color-coded
green -> yellow -> red the same way a battery indicator is."""

from __future__ import annotations

OK_RGBA = (60, 170, 90, 255)
WARN_RGBA = (230, 165, 30, 255)
CRIT_RGBA = (215, 60, 60, 255)
TRACK_RGBA = (120, 120, 120, 90)
ERROR_RGBA = (140, 140, 140, 255)

OK_HEX = "#3caa5a"
WARN_HEX = "#e6a51e"
CRIT_HEX = "#d73c3c"

WARN_THRESHOLD = 70
CRIT_THRESHOLD = 90


def _tier(pct: float) -> str:
    if pct >= CRIT_THRESHOLD:
        return "crit"
    if pct >= WARN_THRESHOLD:
        return "warn"
    return "ok"


def rgba_for(pct: float) -> tuple[int, int, int, int]:
    return {"ok": OK_RGBA, "warn": WARN_RGBA, "crit": CRIT_RGBA}[_tier(pct)]


def hex_for(pct: float) -> str:
    return {"ok": OK_HEX, "warn": WARN_HEX, "crit": CRIT_HEX}[_tier(pct)]
