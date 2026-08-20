"""Small presentation helpers shared by the tray menu and the dashboard."""

from __future__ import annotations

from datetime import datetime, timezone

_PLAN_LABELS = {
    "pro": "Claude Pro",
    "max": "Claude Max",
    "max_5x": "Claude Max (5x)",
    "max_20x": "Claude Max (20x)",
    "team": "Claude Team",
    "enterprise": "Claude Enterprise",
}


def plan_label(subscription_type: str | None) -> str:
    if not subscription_type:
        return "Claude"
    return _PLAN_LABELS.get(subscription_type, f"Claude ({subscription_type})")


def format_countdown(resets_at: datetime | None) -> str:
    if resets_at is None:
        return "unknown"
    seconds = int((resets_at - datetime.now(timezone.utc)).total_seconds())
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


def format_clock(resets_at: datetime | None) -> str:
    if resets_at is None:
        return ""
    return resets_at.astimezone().strftime("%a %H:%M")
