"""OwnerRez MCP server.

Exposes OwnerRez v2 API operations as MCP tools, resources, and prompts:
bookings, in-house guests, guest messaging, webhooks, and read-only financial
lookups (quotes, payments, refunds, fees).

Credentials & options come from the environment (see .env.example):
    OWNERREZ_ACCESS_TOKEN                 # OAuth access token (preferred)
    OWNERREZ_USERNAME + OWNERREZ_TOKEN    # Personal Access Token fallback
    OWNERREZ_READ_ONLY=1                  # block all write tools

Notes on the OwnerRez v2 API (verified live):
  * GET /v2/bookings is bounded by ``since_utc`` (changed-since), plus optional
    ``status`` and ``property_ids`` — it has no arrival date-range filter.
  * GET /v2/guests is bounded by ``created_since_utc``.
  * Messaging uses ``threadId``. There is no endpoint that lists all threads;
    inbound guest messages are delivered via webhooks.
  * OwnerRez does not expose a public expense-creation endpoint.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from .client import OwnerRezClient, OwnerRezError, ReadOnlyError
from .config import Settings
from .store import MessageStore

try:  # optional: load a local .env if python-dotenv is present
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

SETTINGS = Settings.from_env()

mcp = FastMCP(
    name="OwnerRez",
    instructions=(
        "Tools for managing an OwnerRez vacation-rental account: list bookings, "
        "see who is staying now, read financials, message guests, and manage "
        "webhooks. Dates are YYYY-MM-DD; timestamps are UTC ISO-8601; IDs are "
        "OwnerRez numeric IDs. Booking/guest lists are bounded by a 'since' time, "
        "not by stay dates. When the server is in read-only mode, write tools "
        "return an error instead of acting."
    ),
)

_client: Optional[OwnerRezClient] = None
_store: Optional[MessageStore] = None


def client() -> OwnerRezClient:
    global _client
    if _client is None:
        _client = OwnerRezClient(SETTINGS)
    return _client


def store() -> MessageStore:
    global _store
    if _store is None:
        _store = MessageStore(SETTINGS.store_path)
    return _store


def _today() -> str:
    return _dt.date.today().isoformat()


def _utc_days_ago(days: int) -> str:
    return (_dt.datetime.utcnow() - _dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    since_utc: Optional[str] = None,
    status: Optional[str] = "active",
    property_ids: Optional[str] = None,
    arrival_start: Optional[str] = None,
    arrival_end: Optional[str] = None,
    include_guest: bool = True,
    include_charges: bool = False,
    max_items: int = 200,
) -> Dict[str, Any]:
    """List bookings.

    OwnerRez bounds this endpoint by ``since_utc`` (bookings created or changed
    since a UTC time), not by stay dates — so a time bound is always sent. Use
    ``arrival_start`` / ``arrival_end`` to narrow to a stay window client-side.

    Args:
        since_utc: Only bookings changed on/after this UTC time (ISO-8601, e.g.
            2026-01-01T00:00:00Z). Defaults to 180 days ago.
        status: Booking status filter: "active", "canceled", or "pending".
            Defaults to "active"; pass null for all statuses.
        property_ids: Optional comma-separated property IDs to filter by.
        arrival_start: Keep only bookings arriving on/after this date (YYYY-MM-DD).
        arrival_end: Keep only bookings arriving on/before this date (YYYY-MM-DD).
        include_guest: Include guest contact details on each booking.
        include_charges: Include the financial charge breakdown.
        max_items: Safety cap on results.
    """
    if since_utc is None:
        since_utc = _utc_days_ago(180)
    params = {
        "since_utc": since_utc,
        "status": status,
        "property_ids": property_ids,
        "include_guest": str(include_guest).lower(),
        "include_charges": str(include_charges).lower(),
    }
    try:
        bookings = client().get_all("/bookings", params=params, max_items=max_items)
        if arrival_start or arrival_end:
            def _keep(b: Dict[str, Any]) -> bool:
                a = str(b.get("arrival", ""))[:10]
                if not a:
                    return False
                if arrival_start and a < arrival_start:
                    return False
                if arrival_end and a > arrival_end:
                    return False
                return True

            bookings = [b for b in bookings if _keep(b)]
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
    property, guest name, and dates. Defaults to today. Internally pulls active
    bookings changed in the last ~year and filters by stay date.
    """
    on_date = on_date or _today()
    try:
        props = client().get_all("/properties", params={"active": "true"}, max_items=500)
        prop_names = {p.get("id"): (p.get("name") or f"Property {p.get('id')}") for p in props}

        bookings = client().get_all(
            "/bookings",
            params={"since_utc": _utc_days_ago(365), "status": "active", "include_guest": "true"},
            max_items=1000,
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
def find_guest(
    query: Optional[str] = None,
    created_since_utc: Optional[str] = None,
    max_items: int = 100,
) -> Dict[str, Any]:
    """Search or list guests.

    OwnerRez bounds this endpoint by ``created_since_utc``.

    Args:
        query: Optional name/email search term.
        created_since_utc: Only guests created on/after this UTC time (ISO-8601).
            Defaults to 2015-01-01.
        max_items: Safety cap on results.
    """
    params: Dict[str, Any] = {"created_since_utc": created_since_utc or "2015-01-01T00:00:00Z"}
    if query:
        params["q"] = query
    try:
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
# OwnerRez identifies conversations by threadId. There is no endpoint that lists
# all threads — inbound guest messages are delivered via webhooks (subscribe
# with create_webhook_subscription), which is how you discover a threadId.

@mcp.tool
def list_messages(
    thread_id: int,
    include_drafts: bool = False,
    include_attachments: bool = True,
    since_utc: Optional[str] = None,
    max_items: int = 100,
) -> Dict[str, Any]:
    """List the messages in a conversation thread.

    Args:
        thread_id: The OwnerRez conversation/thread ID (``threadId``).
        include_drafts: Include unsent draft messages.
        include_attachments: Include attachment URLs.
        since_utc: Only messages on/after this UTC time (ISO-8601).
        max_items: Safety cap on results.
    """
    params: Dict[str, Any] = {
        "threadId": thread_id,
        "include_drafts": str(include_drafts).lower(),
        "include_attachments": str(include_attachments).lower(),
    }
    if since_utc:
        params["since_utc"] = since_utc
    try:
        rows = client().get_all("/messages", params=params, max_items=max_items)
        return {"ok": True, "thread_id": thread_id, "count": len(rows), "messages": rows}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def send_message(thread_id: int, body: str, attachment_url: Optional[str] = None) -> Dict[str, Any]:
    """Send a message to a guest on an existing conversation thread.

    Args:
        thread_id: The OwnerRez conversation/thread ID (``threadId``). You learn
            this from a booking's conversation or a "message" webhook event.
        body: The message text to send.
        attachment_url: Optional URL to a single image attachment (max ~5MB).

    Blocked when the server is in read-only mode.
    """
    blocked = _guard_write("send a message")
    if blocked:
        return blocked
    payload: Dict[str, Any] = {"threadId": thread_id, "body": body}
    if attachment_url:
        payload["attachment_url"] = attachment_url
    try:
        return {"ok": True, "result": client().post("/messages", json=payload)}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ==================================================================== Webhooks
# Subscribing to "message" events is the supported way to receive inbound guest
# messages (there is no thread-list endpoint to poll).

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

    Subscribe to "message" to receive inbound guest messages (with their
    threadId) for use with list_messages / send_message. Blocked in read-only mode.
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


# ============================================================ Inbox (webhooks)
# These read the local store populated by the webhook receiver
# (`ownerrez-mcp webhook`), giving a real "open messages" inbox. They touch
# local state only — never the OwnerRez API — so they work in read-only mode.

@mcp.tool
def list_open_messages(limit: int = 50) -> Dict[str, Any]:
    """List inbound guest messages captured by the webhook receiver that haven't
    been marked handled yet — your "open messages" inbox.

    Each entry includes its store id, thread_id (use with send_message), guest,
    body, and when it arrived. Requires the webhook receiver to be running and
    subscribed (see create_webhook_subscription with category "message").
    """
    try:
        rows = store().list_open(limit=limit)
        return {"ok": True, "count": len(rows), "open_messages": rows}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def get_message_event(event_id: int) -> Dict[str, Any]:
    """Get one stored message event (including its raw webhook payload) by id."""
    try:
        row = store().get(event_id)
        if row is None:
            return {"ok": False, "error": f"No stored message event with id {event_id}"}
        return {"ok": True, "event": row}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool
def mark_message_handled(event_id: int, handled: bool = True) -> Dict[str, Any]:
    """Mark a stored message as handled (or reopen it), removing it from the
    open list. Local bookkeeping only — does not call OwnerRez."""
    try:
        ok = store().mark_handled(event_id, handled=handled)
        if not ok:
            return {"ok": False, "error": f"No stored message event with id {event_id}"}
        return {"ok": True, "event_id": event_id, "handled": handled}
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
