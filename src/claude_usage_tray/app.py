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

from . import icon as icon_mod
from .api import UsageRequestError, UsageSnapshot, fetch_usage
from .credentials import CredentialsError, load_credentials
from .dashboard import Dashboard
from .formatting import plan_label

log = logging.getLogger(__name__)

POLL_SECONDS = 5 * 60
MIN_POLL_SECONDS = 60
MAX_BACKOFF_SECONDS = 20 * 60
QUEUE_POLL_MS = 150
APP_NAME = "Claude Usage"


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

        self.dashboard = Dashboard(on_refresh=self._request_refresh, on_quit=self._request_quit)

        menu = pystray.Menu(
            Item("Open dashboard", self._on_open_clicked, default=True),
            Item("Refresh now", self._on_refresh_clicked),
            pystray.Menu.SEPARATOR,
            Item("Quit", self._on_quit_clicked),
        )
        self.icon = pystray.Icon(
            "claude-usage-tray",
            icon=icon_mod.render_placeholder(),
            title=APP_NAME,
            menu=menu,
        )

    # -- pystray callbacks (fire on the tray-icon thread) --------------

    def _on_open_clicked(self, _icon=None, _item=None) -> None:
        self._queue.put(("show", _cursor_pos()))

    def _on_refresh_clicked(self, _icon=None, _item=None) -> None:
        self._request_refresh()

    def _on_quit_clicked(self, _icon=None, _item=None) -> None:
        self._request_quit()

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

    def _apply_snapshot(self, snapshot: UsageSnapshot, plan: str) -> None:
        self.dashboard.set_snapshot(snapshot, plan)

        pct = max(
            snapshot.session.utilization_pct if snapshot.session else 0.0,
            snapshot.weekly.utilization_pct if snapshot.weekly else 0.0,
        )
        self.icon.icon = icon_mod.render_gauge(pct)

        session_pct = round(snapshot.session.utilization_pct) if snapshot.session else "?"
        weekly_pct = round(snapshot.weekly.utilization_pct) if snapshot.weekly else "?"
        self.icon.title = f"{plan} · Session {session_pct}% · Weekly {weekly_pct}%"

    def _apply_error(self, message: str) -> None:
        self.dashboard.set_error(message)
        self.icon.icon = icon_mod.render_placeholder()
        self.icon.title = f"{APP_NAME}: {message}"

    def run(self) -> None:
        threading.Thread(target=self._poll_loop, name="usage-poller", daemon=True).start()
        threading.Thread(target=self._icon_loop, name="tray-icon", daemon=True).start()
        self.dashboard.root.after(QUEUE_POLL_MS, self._pump_queue)
        self.dashboard.root.mainloop()


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    TrayApp().run()
