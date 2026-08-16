"""Local SQLite store for inbound OwnerRez message events.

The webhook receiver writes message events here; the MCP tools read them, so
"open messages" becomes a real, push-driven inbox instead of polling an endpoint
OwnerRez doesn't provide. Pure stdlib — no extra dependencies.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS message_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    received_utc TEXT NOT NULL,
    category     TEXT,
    action       TEXT,
    thread_id    TEXT,
    booking_id   TEXT,
    guest        TEXT,
    body         TEXT,
    is_incoming  INTEGER,
    handled      INTEGER NOT NULL DEFAULT 0,
    raw          TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_open ON message_events (handled, category);
"""


def _utcnow() -> str:
    return _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


class MessageStore:
    """Thin SQLite wrapper for message events."""

    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def add_event(self, event: Dict[str, Any]) -> int:
        """Insert a parsed message event; returns the new row id."""
        cur = self._conn.execute(
            """
            INSERT INTO message_events
                (received_utc, category, action, thread_id, booking_id, guest,
                 body, is_incoming, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("received_utc") or _utcnow(),
                event.get("category"),
                event.get("action"),
                _as_text(event.get("thread_id")),
                _as_text(event.get("booking_id")),
                event.get("guest"),
                event.get("body"),
                _as_int_or_none(event.get("is_incoming")),
                json.dumps(event.get("raw"), default=str) if event.get("raw") is not None else None,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_open(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Unhandled message events (inbound or unknown-direction), newest first."""
        rows = self._conn.execute(
            """
            SELECT * FROM message_events
            WHERE handled = 0
              AND (category = 'message' OR category IS NULL)
              AND (is_incoming = 1 OR is_incoming IS NULL)
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get(self, event_id: int) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM message_events WHERE id = ?", (event_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None

    def mark_handled(self, event_id: int, handled: bool = True) -> bool:
        cur = self._conn.execute(
            "UPDATE message_events SET handled = ? WHERE id = ?",
            (1 if handled else 0, event_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def counts(self) -> Dict[str, int]:
        total = self._conn.execute("SELECT COUNT(*) FROM message_events").fetchone()[0]
        open_ = self._conn.execute(
            "SELECT COUNT(*) FROM message_events WHERE handled = 0 "
            "AND (is_incoming = 1 OR is_incoming IS NULL)"
        ).fetchone()[0]
        return {"total": int(total), "open": int(open_)}

    def close(self) -> None:
        self._conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    if d.get("raw"):
        try:
            d["raw"] = json.loads(d["raw"])
        except (ValueError, TypeError):
            pass
    return d


def _as_text(value: Any) -> Optional[str]:
    return None if value is None else str(value)


def _as_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    return 1 if value else 0


# --------------------------------------------------------------------- parsing

def parse_message_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort extraction of a message event from an OwnerRez webhook body.

    OwnerRez payload shapes vary; we pull common fields with fallbacks and always
    keep the raw payload so nothing is lost. Confirm field names against a real
    delivered payload and adjust ``_first`` key lists if needed.
    """
    entity = payload.get("entity") or payload.get("resource") or payload.get("data") or payload

    category = _first(payload, ["category", "type", "resource_type", "event_type"]) or "message"
    action = _first(payload, ["action", "event", "operation"])
    thread_id = _first(entity, ["threadId", "thread_id", "conversation_id", "conversationId"])
    booking_id = _first(entity, ["booking_id", "bookingId", "booking"])
    body = _first(entity, ["body", "message", "text", "content"])

    guest = None
    guest_obj = entity.get("guest") if isinstance(entity, dict) else None
    if isinstance(guest_obj, dict):
        guest = (
            " ".join(x for x in [guest_obj.get("first_name"), guest_obj.get("last_name")] if x).strip()
            or guest_obj.get("name")
        )
    guest = guest or _first(entity, ["guest_name", "from", "sender"])

    is_incoming = _first(entity, ["is_incoming", "incoming", "from_guest", "inbound"])
    direction = _first(entity, ["direction"])
    if is_incoming is None and isinstance(direction, str):
        is_incoming = direction.lower() in ("in", "inbound", "incoming", "from_guest")

    return {
        "category": str(category).lower() if category else None,
        "action": action,
        "thread_id": thread_id,
        "booking_id": booking_id,
        "guest": guest,
        "body": body,
        "is_incoming": is_incoming,
        "raw": payload,
    }


def _first(obj: Any, keys: List[str]) -> Any:
    if not isinstance(obj, dict):
        return None
    for k in keys:
        if k in obj and obj[k] not in (None, ""):
            return obj[k]
    return None
