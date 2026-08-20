"""System tray application.

Three threads:
  - the usage poller (background) hits the Anthropic usage endpoint on a
    timer and posts results to a queue;
  - the tray icon (background) runs pystray's Win32 message loop and posts
    click events to the same queue;
  - the Tk dashboard (main thread) owns the only GUI toolkit that actually
    needs to live on one thread, and drains the queue on a timer via
    ``after()`` -- the standard way to bridge worker threads into Tkinter
    without touching widgets off-thread.
"""

from __future__ import annotations

import ctypes
import logging
import queue
import threading
from ctypes import wintypes

import pystray
from pystray import MenuItem as Item

from . import dpi, icon as icon_mod
from .api import UsageRequestError, UsageSnapshot, Window, fetch_usage
from .credentials import CredentialsError, load_credentials
from .dashboard import Dashboard
from .formatting import plan_label
from .winicon import ClickIcon

log = logging.getLogger(__name__)

POLL_SECONDS = 5 * 60
MIN_POLL_SECONDS = 60
MAX_BACKOFF_SECONDS = 20 * 60
QUEUE_POLL_MS = 150
APP_NAME = "Claude Usage"

# Windows' Shell_NotifyIcon tooltip buffer is capped at 128 characters --
# pystray raises ValueError past that, so error messages (which can be long
# and descriptive in the dashboard) get truncated before going in the title.
MAX_TRAY_TITLE_CHARS = 120

# Same buffer-limit story for balloon/toast notifications: szInfo is a
# WCHAR[256] and szInfoTitle a WCHAR[64] in NOTIFYICONDATAW.
MAX_NOTIFY_TITLE_CHARS = 60
MAX_NOTIFY_MESSAGE_CHARS = 250

NOTIFY_THRESHOLD_PCT = 95


def _cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


class TrayApp:
    def __init__(self, poll_seconds: int = POLL_SECONDS):
        self._poll_seconds = poll_seconds
        self._stop_event = threading.Event()
        self._refresh_event = threading.Event()
        self._queue: queue.Queue = queue.Queue()

        self._notified_session = False
        self._notified_weekly = False

        self.dashboard = Dashboard(on_refresh=self._request_refresh, on_quit=self._request_quit)

        # ClickIcon routes both left- and right-click to this single default
        # item, so the dashboard opens on any click -- Refresh/Quit live as
        # links inside the dashboard itself (see dashboard.py) rather than in
        # a native popup menu the user would have to click through.
        menu = pystray.Menu(Item("Open dashboard", self._on_open_clicked, default=True))
        self.icon = ClickIcon(
            "claude-usage-tray",
            icon=icon_mod.render_placeholder(),
            title=APP_NAME,
            menu=menu,
        )

    # -- pystray callbacks (fire on the tray-icon thread) --------------

    def _on_open_clicked(self, _icon=None, _item=None) -> None:
        self._queue.put(("show", _cursor_pos()))

    def _request_refresh(self) -> None:
        self._refresh_event.set()

    def _request_quit(self) -> None:
        self._stop_event.set()
        self._refresh_event.set()
        self._queue.put(("quit", None))

    # -- usage poller (background thread) --------------------------------

    def _poll_once(self) -> bool:
        try:
            creds = load_credentials()
        except CredentialsError as exc:
            self._queue.put(("error", str(exc)))
            return False

        try:
            snapshot = fetch_usage(creds)
        except UsageRequestError as exc:
            log.warning("usage fetch failed: %s", exc)
            self._queue.put(("error", str(exc)))
            return False

        self._queue.put(("snapshot", (snapshot, plan_label(creds.subscription_type))))
        return True

    def _poll_loop(self) -> None:
        backoff = self._poll_seconds
        while not self._stop_event.is_set():
            ok = self._poll_once()
            backoff = self._poll_seconds if ok else min(backoff * 2, MAX_BACKOFF_SECONDS)
            self._refresh_event.wait(timeout=max(backoff, MIN_POLL_SECONDS))
            self._refresh_event.clear()

    def _icon_loop(self) -> None:
        self.icon.run()

    # -- Tk main loop: the only place dashboard/icon state gets mutated --

    def _pump_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "show":
                    x, y = payload
                    self.dashboard.toggle(x, y)
                elif kind == "snapshot":
                    snapshot, plan = payload
                    self._apply_snapshot(snapshot, plan)
                elif kind == "error":
                    self._apply_error(payload)
                elif kind == "quit":
                    self.icon.stop()
                    self.dashboard.quit()
                    return
        except queue.Empty:
            pass
        self.dashboard.root.after(QUEUE_POLL_MS, self._pump_queue)

    def _set_icon_title(self, text: str) -> None:
        if len(text) > MAX_TRAY_TITLE_CHARS:
            text = text[: MAX_TRAY_TITLE_CHARS - 1] + "…"
        self.icon.title = text

    def _apply_snapshot(self, snapshot: UsageSnapshot, plan: str) -> None:
        self.dashboard.set_snapshot(snapshot, plan)

        pct = max(
            snapshot.session.utilization_pct if snapshot.session else 0.0,
            snapshot.weekly.utilization_pct if snapshot.weekly else 0.0,
        )
        self.icon.icon = icon_mod.render_gauge(pct)

        session_pct = round(snapshot.session.utilization_pct) if snapshot.session else "?"
        weekly_pct = round(snapshot.weekly.utilization_pct) if snapshot.weekly else "?"
        self._set_icon_title(f"{plan} · Session {session_pct}% · Weekly {weekly_pct}%")

        self._check_threshold("session", "Session (5h)", snapshot.session)
        self._check_threshold("weekly", "Weekly (7d)", snapshot.weekly)

    def _apply_error(self, message: str) -> None:
        self.dashboard.set_error(message)
        self.icon.icon = icon_mod.render_placeholder()
        self._set_icon_title(f"{APP_NAME}: {message}")

    # -- 95% usage notifications ------------------------------------------

    def _check_threshold(self, kind: str, label: str, window: Window | None) -> None:
        """Fires a toast once per crossing into >=95% -- not on every poll
        while it stays there -- and re-arms once usage drops back below the
        threshold (e.g. after the window resets)."""

        flag_attr = f"_notified_{kind}"
        if window is None:
            return
        if window.utilization_pct >= NOTIFY_THRESHOLD_PCT:
            if not getattr(self, flag_attr):
                setattr(self, flag_attr, True)
                self._notify_threshold(label, window.utilization_pct)
        else:
            setattr(self, flag_attr, False)

    def _notify_threshold(self, label: str, pct: float) -> None:
        self._send_notification(
            title="Claude usage nearly maxed out",
            message=f"{label} is at {round(pct)}% -- you're close to the limit.",
        )

    def _send_notification(self, title: str, message: str) -> None:
        if len(title) > MAX_NOTIFY_TITLE_CHARS:
            title = title[: MAX_NOTIFY_TITLE_CHARS - 1] + "…"
        if len(message) > MAX_NOTIFY_MESSAGE_CHARS:
            message = message[: MAX_NOTIFY_MESSAGE_CHARS - 1] + "…"
        try:
            self.icon.notify(message, title)
        except Exception:
            log.warning("failed to show notification", exc_info=True)

    def run(self) -> None:
        threading.Thread(target=self._poll_loop, name="usage-poller", daemon=True).start()
        threading.Thread(target=self._icon_loop, name="tray-icon", daemon=True).start()
        self.dashboard.root.after(QUEUE_POLL_MS, self._pump_queue)
        self.dashboard.root.mainloop()


def main() -> None:
    dpi.enable()  # must run before any window (pystray's or Tk's) is created
    logging.basicConfig(level=logging.WARNING)
    TrayApp().run()
