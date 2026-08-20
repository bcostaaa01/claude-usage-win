"""Windows per-process DPI awareness.

Tkinter windows look blurry/pixelated on a scaled Windows display (125%,
150%, ...) unless the process opts into DPI awareness before any window is
created -- otherwise Windows renders at 96 DPI and stretches the resulting
bitmap to fit the real display scale, which is exactly the smeared look.
Call :func:`enable` once, as early as possible in the process (before
pystray's or Tk's window is created); the dashboard then reads :func:`get_dpi`
to scale its own layout to match.
"""

from __future__ import annotations

import ctypes

BASELINE_DPI = 96


def enable() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Vista+ fallback
    except (AttributeError, OSError):
        pass


def get_dpi() -> int:
    try:
        return ctypes.windll.user32.GetDpiForSystem()
    except (AttributeError, OSError):
        return BASELINE_DPI
