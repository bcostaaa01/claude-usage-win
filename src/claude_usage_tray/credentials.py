"""Locate and read the Claude Code OAuth credentials.

Claude Code (the CLI) stores its login token at ``~/.claude/.credentials.json``
after you run ``claude`` and sign in with your Claude.ai account. This module
only reads that file locally -- it never sends the token anywhere except to
Anthropic's own API when checking usage.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


class CredentialsError(RuntimeError):
    """Raised when Claude Code credentials can't be found or parsed."""


def credentials_path() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(override) if override else Path.home() / ".claude"
    return base / ".credentials.json"


@dataclass(frozen=True)
class Credentials:
    access_token: str
    expires_at_ms: int
    subscription_type: str | None
    rate_limit_tier: str | None

    @property
    def is_expired(self) -> bool:
        return time.time() * 1000 >= self.expires_at_ms


def load_credentials() -> Credentials:
    path = credentials_path()
    if not path.exists():
        raise CredentialsError(
            f"No Claude Code credentials found at {path}. "
            "Run `claude` and sign in first."
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CredentialsError(f"Couldn't read {path}: {exc}") from exc

    oauth = raw.get("claudeAiOauth")
    if not oauth or not oauth.get("accessToken"):
        raise CredentialsError(
            "Claude Code credentials file doesn't contain an OAuth access "
            "token. Run `claude` and sign in with /login first."
        )

    return Credentials(
        access_token=oauth["accessToken"],
        expires_at_ms=oauth.get("expiresAt", 0),
        subscription_type=oauth.get("subscriptionType"),
        rate_limit_tier=oauth.get("rateLimitTier"),
    )
