"""System tray application: polls usage in the background and renders it."""

from __future__ import annotations

import logging
import threading
import webbrowser
from datetime import datetime, timezone

import pystray
from pystray import MenuItem as Item

from . import icon as icon_mod
from .api import UsageRequestError, UsageSnapshot, Window, fetch_usage
from .credentials import CredentialsError, load_credentials

log = logging.getLogger(__name__)

POLL_SECONDS = 5 * 60
MIN_POLL_SECONDS = 60
MAX_BACKOFF_SECONDS = 20 * 60
APP_NAME = "Claude Usage"

_PLAN_LABELS = {
    "pro": "Claude Pro",
    "max": "Claude Max",
    "max_5x": "Claude Max (5x)",
    "max_20x": "Claude Max (20x)",
    "team": "Claude Team",
    "enterprise": "Claude Enterprise",
}


def _plan_label(subscription_type: str | None) -> str:
    if not subscription_type:
        return "Claude"
    return _PLAN_LABELS.get(subscription_type, f"Claude ({subscription_type})")


def _format_countdown(resets_at: datetime | None) -> str:
    if resets_at is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    delta = resets_at - now
    seconds = int(delta.total_seconds())
    if seconds <= 0:
        return "any moment"
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours >= 24:
        days = hours // 24
        return f"in {days}d {hours % 24}h"
    if hours:
        return f"in {hours}h {minutes}m"
    return f"in {minutes}m"


def _format_clock(resets_at: datetime | None) -> str:
    if resets_at is None:
        return ""
    local = resets_at.astimezone()
    return local.strftime("%a %H:%M")


def _window_lines(label: str, window: Window | None) -> list[str]:
    if window is None:
        return [f"{label}: n/a"]
    pct = round(window.utilization_pct)
    return [
        f"{label}: {pct}% used",
        f"  resets {_format_countdown(window.resets_at)} ({_format_clock(window.resets_at)})",
    ]


class TrayApp:
    def __init__(self, poll_seconds: int = POLL_SECONDS):
        self._poll_seconds = poll_seconds
        self._stop_event = threading.Event()
        self._refresh_event = threading.Event()
        self._snapshot: UsageSnapshot | None = None
        self._plan_label = "Claude"
        self._error: str | None = None

        self.icon = pystray.Icon(
            "claude-usage-tray",
            icon=icon_mod.render_placeholder(),
            title=APP_NAME,
            menu=self._build_menu(),
        )

    # -- menu -----------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        if self._error:
            return pystray.Menu(
                Item(self._error, None, enabled=False),
                Item("Refresh now", self._on_refresh_clicked),
                Item("Sign in with Claude Code", self._on_open_docs),
                pystray.Menu.SEPARATOR,
                Item("Quit", self._on_quit),
            )

        snap = self._snapshot
        if snap is None:
            return pystray.Menu(
                Item("Loading usage...", None, enabled=False),
                pystray.Menu.SEPARATOR,
                Item("Quit", self._on_quit),
            )

        items = [Item(self._plan_label, None, enabled=False), pystray.Menu.SEPARATOR]
        for line in _window_lines("Session (5h)", snap.session):
            items.append(Item(line, None, enabled=False))
        items.append(pystray.Menu.SEPARATOR)
        for line in _window_lines("Weekly (7d)", snap.weekly):
            items.append(Item(line, None, enabled=False))
        items.append(pystray.Menu.SEPARATOR)
        items.append(Item(f"Last updated {snap.fetched_at.astimezone().strftime('%H:%M:%S')}", None, enabled=False))
        items.append(Item("Refresh now", self._on_refresh_clicked))
        items.append(pystray.Menu.SEPARATOR)
        items.append(Item("Quit", self._on_quit))
        return pystray.Menu(*items)

    # -- actions ----------------------------------------------------------

    def _on_refresh_clicked(self, _icon=None, _item=None) -> None:
        self._refresh_event.set()

    def _on_open_docs(self, _icon=None, _item=None) -> None:
        webbrowser.open("https://docs.claude.com/en/docs/claude-code/overview")

    def _on_quit(self, _icon=None, _item=None) -> None:
        self._stop_event.set()
        self._refresh_event.set()
        self.icon.stop()

    # -- polling ------------------------------------------------------------

    def _apply_snapshot(self, snapshot: UsageSnapshot, plan_label: str) -> None:
        self._snapshot = snapshot
        self._plan_label = plan_label
        self._error = None

        pct = max(
            (snapshot.session.utilization_pct if snapshot.session else 0.0),
            (snapshot.weekly.utilization_pct if snapshot.weekly else 0.0),
        )
        self.icon.icon = icon_mod.render_gauge(pct)

        session_pct = round(snapshot.session.utilization_pct) if snapshot.session else "?"
        weekly_pct = round(snapshot.weekly.utilization_pct) if snapshot.weekly else "?"
        self.icon.title = f"{plan_label} · Session {session_pct}% · Weekly {weekly_pct}%"
        self.icon.menu = self._build_menu()

    def _apply_error(self, message: str) -> None:
        self._error = message
        self.icon.icon = icon_mod.render_placeholder()
        self.icon.title = f"{APP_NAME}: {message}"
        self.icon.menu = self._build_menu()

    def _poll_once(self) -> bool:
        """Fetch usage once. Returns True on success."""
        try:
            creds = load_credentials()
        except CredentialsError as exc:
            self._apply_error(str(exc))
            return False

        try:
            snapshot = fetch_usage(creds)
        except UsageRequestError as exc:
            log.warning("usage fetch failed: %s", exc)
            self._apply_error(str(exc))
            return False

        self._apply_snapshot(snapshot, _plan_label(creds.subscription_type))
        return True

    def _run_loop(self) -> None:
        backoff = self._poll_seconds
        while not self._stop_event.is_set():
            ok = self._poll_once()
            backoff = self._poll_seconds if ok else min(backoff * 2, MAX_BACKOFF_SECONDS)
            self._refresh_event.wait(timeout=max(backoff, MIN_POLL_SECONDS))
            self._refresh_event.clear()

    def run(self) -> None:
        worker = threading.Thread(target=self._run_loop, name="usage-poller", daemon=True)
        worker.start()
        self.icon.run()


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    TrayApp().run()
