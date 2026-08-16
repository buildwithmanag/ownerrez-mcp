"""OwnerRez MCP server.

Exposes OwnerRez v2 API operations as MCP tools, resources, and prompts:
bookings, in-house guests, guest messaging, expenses, webhooks, and read-only
financial lookups (quotes, payments, refunds, fees).

Credentials & options come from the environment (see .env.example):
    OWNERREZ_ACCESS_TOKEN                 # OAuth access token (preferred)
    OWNERREZ_USERNAME + OWNERREZ_TOKEN    # Personal Access Token fallback
    OWNERREZ_READ_ONLY=1                  # block all write tools
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from .client import OwnerRezClient, OwnerRezError, ReadOnlyError
from .config import Settings

try:  # optional: load a local .env if python-dotenv is present
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

SETTINGS = Settings.from_env()

mcp = FastMCP(
    name="OwnerRez",
    instructions=(
        "Tools for managing an OwnerRez vacation-rental account: list current "
        "bookings, see who is staying now, message guests, find open message "
        "threads, record expenses, manage webhooks, and read financials. "
        "Dates are YYYY-MM-DD; IDs are OwnerRez numeric IDs. When the server is "
        "in read-only mode, write tools return an error instead of acting."
    ),
)

_client: Optional[OwnerRezClient] = None


def client() -> OwnerRezClient:
    global _client
    if _client is None:
        _client = OwnerRezClient(SETTINGS)
    return _client


def _today() -> str:
    return _dt.date.today().isoformat()


def _err(exc: Exception) -> Dict[str, Any]:
    if isinstance(exc, ReadOnlyError):
        return {"ok": False, "error": str(exc), "read_only": True}
    if isinstance(exc, OwnerRezError):
        return {
            "ok": False,
            "error": str(exc),
            "status_code": exc.status_code,
            "details": exc.body,
        }
    return {"ok": False, "error": str(exc)}


def _guard_write(action: str) -> Optional[Dict[str, Any]]:
    """Return an error result if writes are disabled, else None."""
    if SETTINGS.read_only:
        return {
            "ok": False,
            "read_only": True,
            "error": (
                f"Cannot {action}: server is running in read-only mode. "
                "Unset OWNERREZ_READ_ONLY to enable writes."
            ),
        }
    return None


# ============================================================ Bookings / stays

@mcp.tool
def list_bookings(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    property_ids: Optional[str] = None,
    include_guest: bool = True,
    include_charges: bool = False,
    max_items: int = 200,
) -> Dict[str, Any]:
    """List current and upcoming bookings.

    Args:
        from_date: Start of the stay window (YYYY-MM-DD). Defaults to today.
        to_date: End of the window (YYYY-MM-DD). Defaults to one year out.
        property_ids: Optional comma-separated property IDs to filter by.
        include_guest: Include guest contact details on each booking.
        include_charges: Include the financial charge breakdown.
        max_items: Safety cap on results.
    """
    from_date = from_date or _today()
    to_date = to_date or (_dt.date.today() + _dt.timedelta(days=365)).isoformat()
    params = {
        "from": from_date,
        "to": to_date,
        "property_ids": property_ids,
        "include_guest": str(include_guest).lower(),
        "include_charges": str(include_charges).lower(),
    }
    try:
        bookings = client().get_all("/bookings", params=params, max_items=max_items)
        return {"ok": True, "count": len(bookings), "bookings": bookings}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def get_booking(booking_id: int, include_guest: bool = True) -> Dict[str, Any]:
    """Get full details for a single booking by its OwnerRez ID."""
    try:
        params = {"include_guest": str(include_guest).lower()}
        return {"ok": True, "booking": client().get(f"/bookings/{booking_id}", params=params)}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def who_is_staying(on_date: Optional[str] = None) -> Dict[str, Any]:
    """Show who is currently staying in each property (in-house guests).

    Returns one row per active stay (arrival <= on_date < departure) with
    property, guest name, and dates. Defaults to today.
    """
    on_date = on_date or _today()
    try:
        props = client().get_all("/properties", params={"active": "true"}, max_items=500)
        prop_names = {p.get("id"): (p.get("name") or f"Property {p.get('id')}") for p in props}

        bookings = client().get_all(
            "/bookings",
            params={"from": on_date, "to": on_date, "include_guest": "true"},
            max_items=500,
        )
        staying: List[Dict[str, Any]] = []
        for b in bookings:
            arrival = str(b.get("arrival", ""))[:10]
            departure = str(b.get("departure", ""))[:10]
            if arrival and departure and arrival <= on_date < departure:
                guest = b.get("guest") or {}
                guest_name = (
                    " ".join(x for x in [guest.get("first_name"), guest.get("last_name")] if x).strip()
                    or guest.get("name")
                    or "Unknown guest"
                )
                staying.append(
                    {
                        "property_id": b.get("property_id"),
                        "property": prop_names.get(b.get("property_id"), "Unknown"),
                        "guest": guest_name,
                        "guest_id": b.get("guest_id"),
                        "booking_id": b.get("id"),
                        "arrival": arrival,
                        "departure": departure,
                        "adults": b.get("adults"),
                        "children": b.get("children"),
                    }
                )
        staying.sort(key=lambda r: r["property"])
        return {"ok": True, "as_of": on_date, "count": len(staying), "staying": staying}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ============================================================ Reference lookups

@mcp.tool
def list_properties(active_only: bool = True, max_items: int = 500) -> Dict[str, Any]:
    """List properties (id, name, address, timezone)."""
    try:
        params = {"active": "true"} if active_only else None
        props = client().get_all("/properties", params=params, max_items=max_items)
        return {"ok": True, "count": len(props), "properties": props}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def list_owners(max_items: int = 500) -> Dict[str, Any]:
    """List property owners (id, name, contact)."""
    try:
        owners = client().get_all("/owners", max_items=max_items)
        return {"ok": True, "count": len(owners), "owners": owners}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def find_guest(query: Optional[str] = None, max_items: int = 100) -> Dict[str, Any]:
    """Search guests by name/email. Omit query to list recent guests."""
    try:
        params = {"q": query} if query else None
        guests = client().get_all("/guests", params=params, max_items=max_items)
        return {"ok": True, "count": len(guests), "guests": guests}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ============================================================ Financials (read)

@mcp.tool
def list_quotes(property_ids: Optional[str] = None, max_items: int = 100) -> Dict[str, Any]:
    """List quotes, optionally filtered to comma-separated property IDs."""
    try:
        params = {"property_ids": property_ids, "include_charges": "true"}
        quotes = client().get_all("/quotes", params=params, max_items=max_items)
        return {"ok": True, "count": len(quotes), "quotes": quotes}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def list_payments(booking_id: Optional[int] = None, max_items: int = 100) -> Dict[str, Any]:
    """List guest payments, optionally for a single booking."""
    try:
        params = {"booking_id": booking_id} if booking_id else None
        rows = client().get_all("/payments", params=params, max_items=max_items)
        return {"ok": True, "count": len(rows), "payments": rows}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def list_refunds(booking_id: Optional[int] = None, max_items: int = 100) -> Dict[str, Any]:
    """List guest refunds, optionally for a single booking."""
    try:
        params = {"booking_id": booking_id} if booking_id else None
        rows = client().get_all("/refunds", params=params, max_items=max_items)
        return {"ok": True, "count": len(rows), "refunds": rows}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def list_fees(booking_id: Optional[int] = None, max_items: int = 100) -> Dict[str, Any]:
    """List booking fees, optionally for a single booking."""
    try:
        params = {"booking_id": booking_id} if booking_id else None
        rows = client().get_all("/fees", params=params, max_items=max_items)
        return {"ok": True, "count": len(rows), "fees": rows}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ==================================================================== Messaging

@mcp.tool
def find_open_messages(
    since_utc: Optional[str] = None,
    unread_only: bool = True,
    max_items: int = 100,
) -> Dict[str, Any]:
    """Find open / recent guest message threads that may need a reply.

    Defaults to threads updated in the last 14 days. NOTE: the exact thread
    listing endpoint is confirmed by the probe (`ownerrez-mcp probe`).
    """
    if since_utc is None:
        since = _dt.datetime.utcnow() - _dt.timedelta(days=14)
        since_utc = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        threads = client().get_all("/threads", params={"since_utc": since_utc}, max_items=max_items)
        if unread_only:
            flagged = [t for t in threads if t.get("is_unread") or t.get("has_unread") or t.get("is_open")]
            threads = flagged if flagged else threads
        return {"ok": True, "count": len(threads), "threads": threads}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def list_messages(thread_id: int, max_items: int = 100) -> Dict[str, Any]:
    """List the messages within a single conversation thread."""
    try:
        rows = client().get_all("/messages", params={"thread_id": thread_id}, max_items=max_items)
        return {"ok": True, "thread_id": thread_id, "count": len(rows), "messages": rows}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def send_message(thread_id: int, body: str, attachment_url: Optional[str] = None) -> Dict[str, Any]:
    """Send a message to a guest on an existing conversation thread.

    Args:
        thread_id: The OwnerRez message thread / conversation ID.
        body: The message text to send.
        attachment_url: Optional URL to a single image attachment (max ~5MB).

    Blocked when the server is in read-only mode.
    """
    blocked = _guard_write("send a message")
    if blocked:
        return blocked
    payload: Dict[str, Any] = {"thread_id": thread_id, "body": body}
    if attachment_url:
        payload["attachment_url"] = attachment_url
    try:
        return {"ok": True, "result": client().post("/messages", json=payload)}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ==================================================================== Expenses

def _create_expense(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    blocked = _guard_write(action)
    if blocked:
        return blocked
    payload = {k: v for k, v in payload.items() if v is not None}
    try:
        return {"ok": True, "expense": client().post("/expenses", json=payload)}
    except OwnerRezError as exc:
        result = _err(exc)
        if exc.status_code in (404, 405, 501):
            result["hint"] = (
                "OwnerRez may not expose a public expense-creation endpoint yet. "
                "Run `ownerrez-mcp probe --probe-writes` to confirm."
            )
        return result
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def add_expense_for_booking(
    booking_id: int,
    amount: float,
    description: str,
    date: Optional[str] = None,
    category: Optional[str] = None,
    vendor: Optional[str] = None,
) -> Dict[str, Any]:
    """Record an expense against a specific booking (e.g. a cleaning charge)."""
    return _create_expense(
        "add an expense",
        {
            "booking_id": booking_id,
            "amount": amount,
            "description": description,
            "date": date or _today(),
            "category": category,
            "vendor": vendor,
        },
    )


@mcp.tool
def add_expense_for_property(
    property_id: int,
    amount: float,
    description: str,
    date: Optional[str] = None,
    category: Optional[str] = None,
    vendor: Optional[str] = None,
) -> Dict[str, Any]:
    """Record an expense against a property (e.g. monthly maintenance)."""
    return _create_expense(
        "add an expense",
        {
            "property_id": property_id,
            "amount": amount,
            "description": description,
            "date": date or _today(),
            "category": category,
            "vendor": vendor,
        },
    )


@mcp.tool
def add_expense_for_owner(
    owner_id: int,
    amount: float,
    description: str,
    property_id: Optional[int] = None,
    date: Optional[str] = None,
    category: Optional[str] = None,
    vendor: Optional[str] = None,
) -> Dict[str, Any]:
    """Record an expense against an owner (charged on their owner statement)."""
    return _create_expense(
        "add an expense",
        {
            "owner_id": owner_id,
            "property_id": property_id,
            "amount": amount,
            "description": description,
            "date": date or _today(),
            "category": category,
            "vendor": vendor,
        },
    )


# ==================================================================== Webhooks

@mcp.tool
def list_webhook_subscriptions(max_items: int = 200) -> Dict[str, Any]:
    """List active webhook subscriptions on the account."""
    try:
        subs = client().get_all("/webhooksubscriptions", max_items=max_items)
        return {"ok": True, "count": len(subs), "subscriptions": subs}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def create_webhook_subscription(url: str, category: str) -> Dict[str, Any]:
    """Subscribe to OwnerRez events by registering an HTTPS callback URL.

    Args:
        url: Your HTTPS endpoint that OwnerRez will POST event payloads to.
        category: Event category (e.g. "booking", "message", "guest").

    Blocked when the server is in read-only mode.
    """
    blocked = _guard_write("create a webhook subscription")
    if blocked:
        return blocked
    try:
        result = client().post("/webhooksubscriptions", json={"url": url, "category": category})
        return {"ok": True, "subscription": result}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def delete_webhook_subscription(subscription_id: int) -> Dict[str, Any]:
    """Remove a webhook subscription by its ID. Blocked in read-only mode."""
    blocked = _guard_write("delete a webhook subscription")
    if blocked:
        return blocked
    try:
        result = client().delete(f"/webhooksubscriptions/{subscription_id}")
        return {"ok": True, "deleted": subscription_id, "result": result}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ==================================================================== Resources

@mcp.resource("ownerrez://properties")
def properties_resource() -> Dict[str, Any]:
    """All properties in the account, as a browsable resource."""
    return {"properties": client().get_all("/properties", max_items=500)}


@mcp.resource("ownerrez://owners")
def owners_resource() -> Dict[str, Any]:
    """All property owners in the account, as a browsable resource."""
    return {"owners": client().get_all("/owners", max_items=500)}


# ==================================================================== Prompts

@mcp.prompt
def draft_checkin_message(guest_name: str, property_name: str, arrival: str) -> str:
    """Draft a warm check-in message for an arriving guest."""
    return (
        f"Write a warm, concise check-in message to {guest_name}, who arrives at "
        f"{property_name} on {arrival}. Include a friendly welcome, a placeholder "
        "for check-in instructions and door code, and an invitation to reach out "
        "with questions. Keep it under 120 words."
    )


@mcp.prompt
def draft_guest_reply(guest_message: str, tone: str = "friendly and professional") -> str:
    """Draft a reply to an incoming guest message."""
    return (
        f"A guest wrote:\n\n\"{guest_message}\"\n\n"
        f"Draft a {tone} reply that directly addresses their question or request. "
        "If information is missing, note what I should fill in before sending."
    )


def run() -> None:
    """Entry point for `ownerrez-mcp serve` / `python server.py`."""
    mcp.run()


if __name__ == "__main__":
    run()
