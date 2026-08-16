"""OAuth authorization-code helper for OwnerRez.

Runs a one-time local flow so users don't have to hand-copy tokens:

    ownerrez-mcp auth

It opens the OwnerRez authorize page, captures the redirect on a local port,
exchanges the code for an access token, and prints the value to paste into
OWNERREZ_ACCESS_TOKEN.

Requires an OwnerRez OAuth app (client id/secret) set via env:
    OWNERREZ_CLIENT_ID, OWNERREZ_CLIENT_SECRET
Optionally override OWNERREZ_REDIRECT_URI / OWNERREZ_AUTHORIZE_URL /
OWNERREZ_TOKEN_URL if OwnerRez changes its endpoints.
"""

from __future__ import annotations

import base64
import secrets as _secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import httpx

from .config import Settings


class _CallbackHandler(BaseHTTPRequestHandler):
    code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.code = (params.get("code") or [None])[0]
        _CallbackHandler.state = (params.get("state") or [None])[0]
        _CallbackHandler.error = (params.get("error") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        msg = "Authorization complete. You can close this tab and return to the terminal."
        if _CallbackHandler.error:
            msg = f"Authorization failed: {_CallbackHandler.error}"
        self.wfile.write(f"<html><body><h3>{msg}</h3></body></html>".encode())

    def log_message(self, *_args):  # silence default logging
        return


def run_oauth_flow(settings: Optional[Settings] = None) -> int:
    settings = settings or Settings.from_env()
    if not settings.client_id or not settings.client_secret:
        print(
            "Missing OAuth app credentials. Set OWNERREZ_CLIENT_ID and "
            "OWNERREZ_CLIENT_SECRET (create an OAuth app in OwnerRez -> "
            "Settings -> API -> OAuth Apps)."
        )
        return 2

    redirect = urllib.parse.urlparse(settings.redirect_uri)
    host = redirect.hostname or "localhost"
    port = redirect.port or 8017
    state = _secrets.token_urlsafe(16)

    authorize_params = {
        "client_id": settings.client_id,
        "redirect_uri": settings.redirect_uri,
        "response_type": "code",
        "state": state,
    }
    authorize_url = settings.authorize_url + "?" + urllib.parse.urlencode(authorize_params)

    print("Opening your browser to authorize OwnerRez access...")
    print(f"If it doesn't open, visit:\n{authorize_url}\n")
    webbrowser.open(authorize_url)

    server = HTTPServer((host, port), _CallbackHandler)
    server.timeout = 300
    server.handle_request()  # blocks for a single callback

    if _CallbackHandler.error:
        print(f"Authorization failed: {_CallbackHandler.error}")
        return 1
    if not _CallbackHandler.code:
        print("No authorization code received (timed out?).")
        return 1
    if _CallbackHandler.state != state:
        print("State mismatch — aborting for safety.")
        return 1

    basic = base64.b64encode(
        f"{settings.client_id}:{settings.client_secret}".encode()
    ).decode()
    resp = httpx.post(
        settings.token_url,
        data={
            "grant_type": "authorization_code",
            "code": _CallbackHandler.code,
            "redirect_uri": settings.redirect_uri,
        },
        headers={
            "Authorization": f"Basic {basic}",
            "Accept": "application/json",
        },
        timeout=30.0,
    )
    if resp.status_code >= 400:
        print(f"Token exchange failed ({resp.status_code}): {resp.text[:300]}")
        return 1

    data = resp.json()
    token = data.get("access_token")
    if not token:
        print(f"No access_token in response: {data}")
        return 1

    print("\nSuccess! Add this to your environment / .env:\n")
    print(f"OWNERREZ_ACCESS_TOKEN={token}")
    return 0
