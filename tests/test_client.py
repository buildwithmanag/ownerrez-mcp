import base64

import httpx
import pytest
import respx

from ownerrez_mcp.client import OwnerRezClient, OwnerRezError, ReadOnlyError
from ownerrez_mcp.config import Settings

BASE = "https://api.ownerrez.com/v2"


def make_client(settings: Settings) -> OwnerRezClient:
    # No real sleeping during retry tests.
    return OwnerRezClient(settings, sleep=lambda _s: None)


def test_bearer_auth_header(oauth_settings):
    client = make_client(oauth_settings)
    assert client._base_headers()["Authorization"] == "Bearer SECRET-OAUTH-TOKEN"


def test_basic_auth_header(pat_settings):
    client = make_client(pat_settings)
    expected = "Basic " + base64.b64encode(b"me@example.com:SECRET-PAT").decode()
    assert client._base_headers()["Authorization"] == expected


def test_missing_credentials_raises():
    with pytest.raises(ValueError):
        OwnerRezClient(Settings())


@respx.mock
def test_pagination_follows_next_page(oauth_settings):
    route = respx.get(url__startswith=f"{BASE}/properties")
    route.side_effect = [
        httpx.Response(
            200,
            json={"items": [{"id": 1}], "next_page_url": f"{BASE}/properties?page=2"},
        ),
        httpx.Response(200, json={"items": [{"id": 2}], "next_page_url": None}),
    ]
    client = make_client(oauth_settings)
    rows = client.get_all("/properties")
    assert [r["id"] for r in rows] == [1, 2]
    assert route.call_count == 2


@respx.mock
def test_error_redacts_secret(oauth_settings):
    respx.get(f"{BASE}/bookings").mock(
        return_value=httpx.Response(401, json={"message": "invalid token SECRET-OAUTH-TOKEN"})
    )
    client = make_client(oauth_settings)
    with pytest.raises(OwnerRezError) as exc:
        client.get("/bookings")
    assert "SECRET-OAUTH-TOKEN" not in str(exc.value)
    assert "***" in str(exc.value)


@respx.mock
def test_retries_on_429_then_succeeds(oauth_settings):
    route = respx.get(f"{BASE}/owners")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"items": [{"id": 7}], "next_page_url": None}),
    ]
    client = make_client(oauth_settings)
    rows = client.get_all("/owners")
    assert rows == [{"id": 7}]
    assert route.call_count == 2


@respx.mock
def test_read_only_blocks_writes():
    respx.post(f"{BASE}/messages").mock(return_value=httpx.Response(200, json={}))
    settings = Settings(access_token="T", read_only=True)
    client = make_client(settings)
    with pytest.raises(ReadOnlyError):
        client.post("/messages", json={"body": "hi"})
