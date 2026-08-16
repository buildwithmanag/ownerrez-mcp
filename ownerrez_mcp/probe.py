"""Live OwnerRez API probe: confirm which endpoints your token can reach.

    ownerrez-mcp probe

Uses the correct v2 parameters (since_utc for bookings, created_since_utc for
guests, threadId for messages). Read-only and safe.
"""

from __future__ import annotations

import argparse
from typing import List, Optional

from .client import OwnerRezClient, OwnerRezError
from .config import Settings


def _probe_get(client: OwnerRezClient, path: str, params=None) -> str:
    try:
        data = client.get(path, params=params)
        if isinstance(data, dict) and "items" in data:
            return f"OK  200  ~{len(data.get('items') or [])} item(s) (count={data.get('count')})"
        if isinstance(data, list):
            return f"OK  200  {len(data)} item(s)"
        return "OK  200  (object)"
    except OwnerRezError as exc:
        return f"ERR {exc.status_code}  {str(exc)[:260]}"
    except Exception as exc:  # noqa: BLE001
        return f"ERR ---  {exc}"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="ownerrez-mcp probe", description="Probe the OwnerRez v2 API.")
    parser.parse_args(argv)  # accepts -h/--help; no other options

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    client = OwnerRezClient(Settings.from_env())

    print("=" * 68)
    print("OwnerRez API probe  (base:", client.base_url + ")")
    if client.settings.read_only:
        print("read-only mode: ON")
    print("=" * 68)

    checks = [
        ("bookings (list)", "/bookings", {"since_utc": "2024-01-01T00:00:00Z", "status": "active"}),
        ("properties (list)", "/properties", None),
        ("owners (list)", "/owners", None),
        ("guests (list)", "/guests", {"created_since_utc": "2015-01-01T00:00:00Z"}),
        ("quotes (list)", "/quotes", None),
        ("payments (list)", "/payments", None),
        ("webhooksubscriptions", "/webhooksubscriptions", None),
    ]
    for label, path, params in checks:
        print(f"{label:24s} {_probe_get(client, path, params)}")

    print("-" * 68)
    print("Messaging: GET /v2/messages needs a threadId (learned from a 'message'")
    print("webhook), so it isn't probed here. Expenses have no public v2 endpoint.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
