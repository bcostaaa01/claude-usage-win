"""Client for Anthropic's (unofficial) OAuth usage endpoint.

Claude Code's own status line calls ``GET /api/oauth/usage`` on
api.anthropic.com, authenticated with the same OAuth bearer token it uses
for chat requests, to show session/weekly quota. This isn't publicly
documented and could change or disappear without notice -- treat it as
best-effort.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from . import __version__
from .credentials import Credentials

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
REQUEST_TIMEOUT_SECONDS = 10


class UsageRequestError(RuntimeError):
    """Raised when the usage endpoint can't be reached or parsed."""

    def __init__(self, message: str, *, rate_limited: bool = False, auth_failed: bool = False):
        super().__init__(message)
        self.rate_limited = rate_limited
        self.auth_failed = auth_failed


@dataclass(frozen=True)
class Window:
    """A single usage window, e.g. the rolling 5-hour session limit."""

    utilization_pct: float
    resets_at: datetime | None


@dataclass(frozen=True)
class UsageSnapshot:
    session: Window | None  # five_hour
    weekly: Window | None  # seven_day
    weekly_opus: Window | None
    weekly_sonnet: Window | None
    fetched_at: datetime


def _parse_window(data: dict | None) -> Window | None:
    if not data:
        return None
    resets_raw = data.get("resets_at")
    resets_at = None
    if resets_raw:
        try:
            resets_at = datetime.fromisoformat(resets_raw)
        except ValueError:
            resets_at = None
    return Window(utilization_pct=float(data.get("utilization", 0.0)), resets_at=resets_at)


def fetch_usage(creds: Credentials) -> UsageSnapshot:
    request = urllib.request.Request(
        USAGE_URL,
        method="GET",
        headers={
            "Authorization": f"Bearer {creds.access_token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
            # An empty/missing User-Agent routes into a much stricter rate
            # limit bucket for this endpoint; mimic Claude Code's own.
            "User-Agent": f"claude-cli/{__version__} (claude-usage-tray)",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise UsageRequestError(
                "Anthropic is rate-limiting usage checks right now. This should "
                "clear on its own in a few minutes -- avoid refreshing repeatedly "
                "in the meantime.",
                rate_limited=True,
            ) from exc
        if exc.code in (401, 403):
            raise UsageRequestError(
                "Not authorized -- your Claude Code login may have expired. "
                "Run `claude` and sign in again.",
                auth_failed=True,
            ) from exc
        raise UsageRequestError(f"Usage endpoint returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise UsageRequestError(f"Couldn't reach Anthropic: {exc.reason}") from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise UsageRequestError(f"Bad response from usage endpoint: {exc}") from exc

    return UsageSnapshot(
        session=_parse_window(body.get("five_hour")),
        weekly=_parse_window(body.get("seven_day")),
        weekly_opus=_parse_window(body.get("seven_day_opus")),
        weekly_sonnet=_parse_window(body.get("seven_day_sonnet")),
        fetched_at=datetime.now(timezone.utc),
    )
