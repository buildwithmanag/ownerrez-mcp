"""Tests for tool logic using an injected fake client (no network)."""

import ownerrez_mcp.server as server


class FakeClient:
    def __init__(self, data=None, calls=None):
        self.data = data or {}
        self.calls = calls if calls is not None else []

    def get_all(self, path, params=None, max_items=500):
        return self.data.get(path, [])

    def get(self, path, params=None):
        return self.data.get(path)

    def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        return {"id": 999, **(json or {})}

    def delete(self, path):
        self.calls.append(("DELETE", path))
        return None


def use_fake(monkeypatch, data=None, calls=None, read_only=False):
    fake = FakeClient(data=data, calls=calls)
    monkeypatch.setattr(server, "_client", fake)
    monkeypatch.setattr(server, "client", lambda: fake)
    monkeypatch.setattr(server.SETTINGS, "read_only", read_only)
    return fake


def test_who_is_staying_filters_active(monkeypatch):
    data = {
        "/properties": [{"id": 1, "name": "Beach House"}, {"id": 2, "name": "Cabin"}],
        "/bookings": [
            {  # active
                "id": 100, "property_id": 1, "guest_id": 5,
                "arrival": "2026-08-10", "departure": "2026-08-20",
                "guest": {"first_name": "Ada", "last_name": "Lovelace"},
            },
            {  # already departed
                "id": 101, "property_id": 2, "guest_id": 6,
                "arrival": "2026-08-01", "departure": "2026-08-05",
                "guest": {"first_name": "Alan", "last_name": "Turing"},
            },
        ],
    }
    use_fake(monkeypatch, data=data)
    result = server.who_is_staying(on_date="2026-08-16")
    assert result["ok"] is True
    assert result["count"] == 1
    row = result["staying"][0]
    assert row["property"] == "Beach House"
    assert row["guest"] == "Ada Lovelace"


def test_send_message_success(monkeypatch):
    calls = []
    use_fake(monkeypatch, calls=calls)
    result = server.send_message(thread_id=42, body="Hello!")
    assert result["ok"] is True
    # OwnerRez uses camelCase threadId in the message payload.
    assert calls == [("POST", "/messages", {"threadId": 42, "body": "Hello!"})]


def test_send_message_blocked_in_read_only(monkeypatch):
    calls = []
    use_fake(monkeypatch, calls=calls, read_only=True)
    result = server.send_message(thread_id=42, body="Hello!")
    assert result["ok"] is False
    assert result["read_only"] is True
    assert calls == []  # never hit the API


def test_create_webhook_blocked_in_read_only(monkeypatch):
    calls = []
    use_fake(monkeypatch, calls=calls, read_only=True)
    result = server.create_webhook_subscription(url="https://x.example/hook", category="message")
    assert result["ok"] is False
    assert result["read_only"] is True
    assert calls == []
