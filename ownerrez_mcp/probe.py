"""Live OwnerRez API probe: confirm which endpoints your token can reach.

    ownerrez-mcp probe                 # read-only checks (safe)
    ownerrez-mcp probe --probe-writes  # also test the expense POST endpoint
                                       # with an invalid body (creates nothing)
"""

from __future__ import annotations

import argparse
import json
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
        return f"ERR {exc.status_code}  {str(exc)[:120]}"
    except Exception as exc:  # noqa: BLE001
        return f"ERR ---  {exc}"


def _probe_expense_write(client: OwnerRezClient) -> str:
    try:
        result = client.post("/expenses", json={"__probe__": True})
        return f"UNEXPECTED 2xx (may have created a record!): {json.dumps(result)[:160]}"
    except OwnerRezError as exc:
        if exc.status_code in (400, 422):
            return f"WRITABLE  {exc.status_code}  endpoint exists, rejected invalid body (good)"
        if exc.status_code in (404, 405, 501):
            return f"NOT SUPPORTED  {exc.status_code}  no public expense-create endpoint"
        if exc.status_code in (401, 403):
            return f"AUTH/SCOPE  {exc.status_code}  token lacks permission for expenses"
        return f"OTHER {exc.status_code}  {str(exc)[:120]}"
    except Exception as exc:  # noqa: BLE001
        return f"ERR ---  {exc}"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="ownerrez-mcp probe", description="Probe the OwnerRez v2 API.")
    parser.add_argument(
        "--probe-writes",
        action="store_true",
        help="Also test the expense POST endpoint with an invalid (non-creating) body.",
    )
    args = parser.parse_args(argv)

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    client = OwnerRezClient(Settings.from_env())

    print("=" * 68)
    print("OwnerRez API probe  (base:", client.base_url + ")")
    if client.settings.read_only:
        print("read-only mode: ON (write probe will be skipped)")
    print("=" * 68)

    read_checks = [
        ("bookings (list)", "/bookings", {"from": "2000-01-01", "to": "2100-01-01"}),
        ("properties (list)", "/properties", None),
        ("owners (list)", "/owners", None),
        ("guests (list)", "/guests", None),
        ("quotes (list)", "/quotes", None),
        ("payments (list)", "/payments", None),
        ("threads (list)", "/threads", None),
        ("messages (list)", "/messages", None),
        ("expenses (list)", "/expenses", None),
        ("webhooksubscriptions", "/webhooksubscriptions", None),
    ]
    for label, path, params in read_checks:
        print(f"{label:24s} {_probe_get(client, path, params)}")

    if args.probe_writes and not client.settings.read_only:
        print("-" * 68)
        print(f"{'expenses (POST probe)':24s} {_probe_expense_write(client)}")

    print("=" * 68)
    print("'threads'/'messages'/'expenses' results tell us what the server can")
    print("rely on. Re-run with --probe-writes to test the expense POST endpoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
