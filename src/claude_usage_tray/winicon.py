"""A pystray Icon where *any* click opens the dashboard directly.

Stock pystray only auto-invokes the menu's default item on a **left**
click; a right click always pops its plain, unstylable native menu, which
means an extra "click Open dashboard inside the menu" step. Native Windows
tray flyouts (network, volume, battery, OneDrive) don't work that way --
one click, either button, shows the panel -- so we reach into pystray's
private Win32 message handler to match that.

This depends on pystray internals (``_on_notify``, ``pystray._util.win32``)
that could change between releases; if the import shape moves, we fall
back to stock pystray.Icon (right click shows its native menu) instead of
crashing.
"""

from __future__ import annotations

import pystray

try:
    from pystray._util import win32 as _win32util

    class ClickIcon(pystray.Icon):
        def _on_notify(self, wparam, lparam):
            if lparam in (_win32util.WM_LBUTTONUP, _win32util.WM_RBUTTONUP):
                self()

except ImportError:
    ClickIcon = pystray.Icon
