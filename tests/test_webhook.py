import pytest

from ownerrez_mcp.config import Settings
from ownerrez_mcp.store import MessageStore

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from ownerrez_mcp.webhook import build_app  # noqa: E402


def _client(tmp_path, **kw):
    settings = Settings(store_path=str(tmp_path / "m.db"), **kw)
    store = MessageStore(settings.store_path)
    app = build_app(settings, store=store)
    return TestClient(app), store


def test_post_message_is_stored(tmp_path):
    client, store = _client(tmp_path)
    resp = client.post("/", json={"category": "message", "entity": {"threadId": 12, "body": "hi", "direction": "inbound"}})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert store.counts()["open"] == 1


def test_get_health_and_challenge(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/").json()["service"] == "ownerrez-webhook"
    # GET validation challenge is echoed back verbatim.
    assert client.get("/?validationToken=abc123").text == "abc123"


def test_secret_enforced(tmp_path):
    client, store = _client(tmp_path, webhook_secret="s3cret")
    # Missing secret -> rejected, nothing stored.
    assert client.post("/", json={"category": "message", "entity": {"body": "x"}}).status_code == 401
    assert store.counts()["total"] == 0
    # Correct secret -> accepted.
    ok = client.post(
        "/",
        headers={"X-Webhook-Secret": "s3cret"},
        json={"category": "message", "entity": {"body": "x", "direction": "inbound"}},
    )
    assert ok.status_code == 200
    assert store.counts()["open"] == 1
