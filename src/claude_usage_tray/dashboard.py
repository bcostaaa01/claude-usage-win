"""A small always-on-top flyout dashboard shown near the tray icon.

Native Win32 tray context menus can't be styled (plain text, no colors, no
bars), so the right-click menu stays minimal and this custom Tk popup -- a
dark rounded card with colored progress bars -- carries the actual detail,
the same way OneDrive/Dropbox pop a small panel above their tray icon.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from . import colors, dpi
from .api import UsageSnapshot, Window
from .formatting import format_clock, format_countdown

_BG_CARD = "#1e1f22"
_BORDER = "#3a3b3e"
_FG_PRIMARY = "#f2f2f2"
_FG_SECONDARY = "#c7cad1"
_FG_MUTED = "#8a8e94"
_FG_FAINT = "#6f7378"
_TRACK = "#2c2d31"
_LINK_REFRESH = "#8ab4f8"
_LINK_REFRESH_HOVER = "#b7d3fc"
_LINK_QUIT = "#d77a7a"
_LINK_QUIT_HOVER = "#eca3a3"
_WARN = "#e6a51e"
_HOVER_BG = "#303136"

_FONT = "Segoe UI"


def _rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class Dashboard:
    """Owns the Tk root. Must only be touched from the thread running
    ``root.mainloop()`` (see app.py's queue-pump pattern).

    All layout numbers below are logical (96-DPI) pixels; :meth:`_s` scales
    them to the real display DPI so the card renders crisp -- rather than
    stretched/blurry -- at 125%/150%/etc scaling. ``dpi.enable()`` must have
    already run (app.py's ``main()`` does this) before this is constructed.
    """

    _MAGIC = "#ff00fe"  # chroma-key color -> made transparent for rounded corners

    def __init__(self, *, on_refresh: Callable[[], None], on_quit: Callable[[], None]):
        self._on_refresh = on_refresh
        self._on_quit = on_quit
        self._snapshot: UsageSnapshot | None = None
        self._plan = "Claude"
        self._error: str | None = None
        self._visible = False
        self._loading = False
        self._spin_angle = 0
        self._spin_job: str | None = None
        self._spinner_item: int | None = None

        display_dpi = dpi.get_dpi()
        self.scale = display_dpi / dpi.BASELINE_DPI
        self.WIDTH = self._s(300)
        self.HEIGHT = self._s(224)
        self.MARGIN = self._s(10)
        self.RADIUS = self._s(16)

        self.root = tk.Tk()
        self.root.tk.call("tk", "scaling", display_dpi / 72.0)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=self._MAGIC)
        self.root.attributes("-transparentcolor", self._MAGIC)
        self.root.withdraw()
        self.root.bind("<Escape>", lambda _e: self.hide())
        self.root.bind("<FocusOut>", lambda _e: self.hide())

        self.canvas = tk.Canvas(
            self.root,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg=self._MAGIC,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack()
        self._render()

    def _s(self, px: float) -> int:
        """Scale a logical (96-DPI) pixel measurement to the real display."""
        return round(px * self.scale)

    def _add_hover(
        self,
        c: tk.Canvas,
        text_item: int,
        *,
        normal_fg: str,
        hover_fg: str,
        on_click: Callable[[], None],
        pad: int | None = None,
    ) -> None:
        """Gives a text item a pill-shaped hover highlight, a brighter
        color, and a hand cursor -- so it reads as a clickable button
        rather than plain text, and gives a bigger, more forgiving hit
        target than the glyph/text bounds alone."""

        pad = self._s(6) if pad is None else pad
        x1, y1, x2, y2 = c.bbox(text_item)
        radius = (y2 - y1 + 2 * pad) / 2
        bg = _rounded_rect(
            c, x1 - pad, y1 - pad, x2 + pad, y2 + pad,
            radius, fill=_BG_CARD, outline="",
        )
        c.tag_lower(bg, text_item)

        def _enter(_e=None):
            c.itemconfig(bg, fill=_HOVER_BG)
            c.itemconfig(text_item, fill=hover_fg)
            c.config(cursor="hand2")

        def _leave(_e=None):
            c.itemconfig(bg, fill=_BG_CARD)
            c.itemconfig(text_item, fill=normal_fg)
            c.config(cursor="")

        for item in (bg, text_item):
            c.tag_bind(item, "<Enter>", _enter)
            c.tag_bind(item, "<Leave>", _leave)
            c.tag_bind(item, "<Button-1>", lambda _e: on_click())

    # -- state updates (call only from the Tk thread) --------------------

    def set_snapshot(self, snapshot: UsageSnapshot, plan: str) -> None:
        self._stop_spinner()
        self._snapshot = snapshot
        self._plan = plan
        self._error = None
        self._render()

    def set_error(self, message: str) -> None:
        self._stop_spinner()
        self._error = message
        self._render()

    # -- manual refresh spinner --------------------------------------------

    def _start_refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._spin_angle = 0
        self._render()
        self._tick_spinner()
        self._on_refresh()

    def _tick_spinner(self) -> None:
        if not self._loading or self._spinner_item is None:
            return
        self._spin_angle = (self._spin_angle + 30) % 360
        self.canvas.itemconfig(self._spinner_item, start=self._spin_angle)
        self._spin_job = self.root.after(60, self._tick_spinner)

    def _stop_spinner(self) -> None:
        self._loading = False
        self._spinner_item = None
        if self._spin_job is not None:
            self.root.after_cancel(self._spin_job)
            self._spin_job = None

    # -- visibility -------------------------------------------------------

    def toggle(self, x: int, y: int) -> None:
        self.hide() if self._visible else self.show(x, y)

    def show(self, x: int, y: int) -> None:
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        left = min(max(x - self.WIDTH + self._s(40), 0), max(sw - self.WIDTH, 0))
        top = min(max(y - self.HEIGHT - self._s(12), 0), max(sh - self.HEIGHT, 0))
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{left}+{top}")
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self._visible = True

    def hide(self) -> None:
        self.root.withdraw()
        self._visible = False

    def quit(self) -> None:
        self.root.quit()

    # -- drawing ------------------------------------------------------------

    def _render(self) -> None:
        c = self.canvas
        c.delete("all")

        x1, y1 = self.MARGIN, self.MARGIN
        x2, y2 = self.WIDTH - self.MARGIN, self.HEIGHT - self.MARGIN
        _rounded_rect(c, x1, y1, x2, y2, self.RADIUS, fill=_BG_CARD, outline=_BORDER, width=self._s(1))

        pad = self._s(18)
        y = y1 + pad

        c.create_text(x1 + pad, y, anchor="nw", text=self._plan, fill=_FG_PRIMARY, font=(_FONT, 11, "bold"))
        close = c.create_text(x2 - pad, y, anchor="ne", text="✕", fill=_FG_MUTED, font=(_FONT, 10))
        self._add_hover(c, close, normal_fg=_FG_MUTED, hover_fg=_FG_PRIMARY, on_click=self.hide)
        y += self._s(28)

        if self._error:
            c.create_text(
                x1 + pad, y, anchor="nw", text=self._error, fill=_WARN,
                font=(_FONT, 9), width=self.WIDTH - 2 * pad - 2 * self.MARGIN,
            )
        elif self._snapshot is None:
            c.create_text(x1 + pad, y, anchor="nw", text="Loading usage...", fill=_FG_MUTED, font=(_FONT, 9))
        else:
            y = self._draw_metric(c, x1 + pad, y, x2 - pad, "Session (5h)", self._snapshot.session)
            y += self._s(10)
            self._draw_metric(c, x1 + pad, y, x2 - pad, "Weekly (7d)", self._snapshot.weekly)

        footer_y = y2 - pad
        updated = ""
        if self._snapshot is not None:
            updated = f"Updated {self._snapshot.fetched_at.astimezone().strftime('%H:%M:%S')}"
        c.create_text(x1 + pad, footer_y, anchor="sw", text=updated, fill=_FG_FAINT, font=(_FONT, 8))

        if self._loading:
            label = c.create_text(
                x2 - pad - self._s(38), footer_y, anchor="se", text="Refreshing…",
                fill=_FG_FAINT, font=(_FONT, 9),
            )
            lx1, ly1, _lx2, ly2 = c.bbox(label)
            r = self._s(5)
            cx, cy = lx1 - self._s(8) - r, (ly1 + ly2) / 2
            self._spinner_item = c.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=self._spin_angle, extent=270, style="arc",
                outline=_LINK_REFRESH, width=max(self._s(2), 2),
            )
        else:
            refresh = c.create_text(
                x2 - pad - self._s(38), footer_y, anchor="se", text="Refresh",
                fill=_LINK_REFRESH, font=(_FONT, 9, "underline"),
            )
            self._add_hover(c, refresh, normal_fg=_LINK_REFRESH, hover_fg=_LINK_REFRESH_HOVER, on_click=self._start_refresh)

        quit_ = c.create_text(
            x2 - pad, footer_y, anchor="se", text="Quit",
            fill=_LINK_QUIT, font=(_FONT, 9, "underline"),
        )
        self._add_hover(c, quit_, normal_fg=_LINK_QUIT, hover_fg=_LINK_QUIT_HOVER, on_click=self._on_quit)

    def _draw_metric(self, c: tk.Canvas, xl: int, y: int, xr: int, label: str, window: Window | None) -> int:
        pct = round(window.utilization_pct) if window else 0
        color = colors.hex_for(pct) if window else _FG_FAINT

        c.create_text(xl, y, anchor="nw", text=label, fill=_FG_SECONDARY, font=(_FONT, 9))
        c.create_text(xr, y, anchor="ne", text=f"{pct}%" if window else "n/a", fill=color, font=(_FONT, 9, "bold"))
        y += self._s(18)

        bar_h = self._s(8)
        _rounded_rect(c, xl, y, xr, y + bar_h, bar_h / 2, fill=_TRACK, outline="")
        if window and pct > 0:
            fill_w = max((xr - xl) * min(pct, 100) / 100, bar_h)
            _rounded_rect(c, xl, y, xl + fill_w, y + bar_h, bar_h / 2, fill=color, outline="")
        y += bar_h + self._s(12)

        detail = f"resets {format_countdown(window.resets_at)} · {format_clock(window.resets_at)}" if window else "no data"
        c.create_text(xl, y, anchor="nw", text=detail, fill=_FG_MUTED, font=(_FONT, 8))
        y += self._s(18)
        return y
