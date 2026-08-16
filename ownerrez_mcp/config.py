"""Configuration for the OwnerRez MCP server, loaded from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

DEFAULT_BASE_URL = "https://api.ownerrez.com/v2"
DEFAULT_STORE_PATH = os.path.join(
    os.path.expanduser("~"), ".ownerrez-mcp", "messages.db"
)
# OAuth endpoints. These defaults follow OwnerRez's documented OAuth app flow;
# override via env if OwnerRez changes them.
DEFAULT_AUTHORIZE_URL = "https://app.ownerrez.com/oauth/authorize"
DEFAULT_TOKEN_URL = "https://api.ownerrez.com/oauth/access_token"
DEFAULT_REDIRECT_URI = "http://localhost:8017/callback"


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _as_int(value: Optional[str], default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _as_float(value: Optional[str], default: float) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    """Resolved runtime configuration."""

    base_url: str = DEFAULT_BASE_URL
    access_token: Optional[str] = None
    username: Optional[str] = None
    token: Optional[str] = None

    read_only: bool = False
    max_retries: int = 3
    timeout: float = 30.0

    # Webhook receiver + local message store.
    store_path: str = DEFAULT_STORE_PATH
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8000
    webhook_secret: Optional[str] = None

    # OAuth app (used only by the `auth` helper).
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: str = DEFAULT_REDIRECT_URI
    authorize_url: str = DEFAULT_AUTHORIZE_URL
    token_url: str = DEFAULT_TOKEN_URL

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            base_url=(os.getenv("OWNERREZ_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
            access_token=os.getenv("OWNERREZ_ACCESS_TOKEN") or None,
            username=os.getenv("OWNERREZ_USERNAME") or None,
            token=os.getenv("OWNERREZ_TOKEN") or None,
            read_only=_as_bool(os.getenv("OWNERREZ_READ_ONLY"), False),
            max_retries=_as_int(os.getenv("OWNERREZ_MAX_RETRIES"), 3),
            timeout=_as_float(os.getenv("OWNERREZ_TIMEOUT"), 30.0),
            store_path=os.getenv("OWNERREZ_STORE") or DEFAULT_STORE_PATH,
            webhook_host=os.getenv("OWNERREZ_WEBHOOK_HOST") or "0.0.0.0",
            webhook_port=_as_int(os.getenv("OWNERREZ_WEBHOOK_PORT"), 8000),
            webhook_secret=os.getenv("OWNERREZ_WEBHOOK_SECRET") or None,
            client_id=os.getenv("OWNERREZ_CLIENT_ID") or None,
            client_secret=os.getenv("OWNERREZ_CLIENT_SECRET") or None,
            redirect_uri=os.getenv("OWNERREZ_REDIRECT_URI") or DEFAULT_REDIRECT_URI,
            authorize_url=os.getenv("OWNERREZ_AUTHORIZE_URL") or DEFAULT_AUTHORIZE_URL,
            token_url=os.getenv("OWNERREZ_TOKEN_URL") or DEFAULT_TOKEN_URL,
        )

    def has_credentials(self) -> bool:
        return bool(self.access_token or (self.username and self.token))

    def secrets(self) -> List[str]:
        """Secret values that must never appear in logs or error output."""
        return [
            s
            for s in (self.access_token, self.token, self.client_secret, self.webhook_secret)
            if s
        ]
