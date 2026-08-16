"""Webhook receiver for inbound OwnerRez events (FastAPI).

Run it, expose it on a public HTTPS URL (e.g. an ngrok/cloudflared tunnel or a
small deploy), then subscribe with `create_webhook_subscription(url=..., category="message")`.
Incoming message events are parsed and written to the local store, where the
`list_open_messages` MCP tool can read them.

    ownerrez-mcp webhook            # listen on 0.0.0.0:8000 (configurable)

Optional shared-secret protection: set OWNERREZ_WEBHOOK_SECRET and include it as
an `X-Webhook-Secret` header or `?secret=` query param when you register the URL.
Always run behind HTTPS.

Requires the optional extra:  pip install "ownerrez-mcp[webhook]"
"""

# NOTE: no `from __future__ import annotations` here — FastAPI must see the real
# `Request` class in the route annotations, not a stringized forward-ref.

from typing import Any, Optional

from .config import Settings
from .store import MessageStore, parse_message_event

# Keys OwnerRez / providers use for a subscription validation handshake.
_VALIDATION_KEYS = ("validationToken", "validation_token", "challenge", "validation")


def _extract_validation(mapping: Any) -> Optional[str]:
    if not isinstance(mapping, dict):
        return None
    for k in _VALIDATION_KEYS:
        if mapping.get(k):
            return str(mapping[k])
    return None


def build_app(settings: Optional[Settings] = None, store: Optional[MessageStore] = None):
    """Construct the FastAPI app. Imported lazily so the core install stays lean."""
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, PlainTextResponse

    settings = settings or Settings.from_env()
    store = store or MessageStore(settings.store_path)

    app = FastAPI(title="OwnerRez Webhook Receiver", version="1.0")

    def _authorized(request: "Request") -> bool:
        if not settings.webhook_secret:
            return True
        supplied = request.headers.get("x-webhook-secret") or request.query_params.get("secret")
        return supplied == settings.webhook_secret

    @app.get("/")
    async def health(request: Request):
        # Some providers validate a subscription with a GET challenge.
        token = _extract_validation(dict(request.query_params))
        if token:
            return PlainTextResponse(token)
        return {"ok": True, "service": "ownerrez-webhook", **store.counts()}

    @app.post("/")
    async def receive(request: Request):
        if not _authorized(request):
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

        try:
            payload = await request.json()
        except Exception:
            payload = {}

        # Subscription validation handshake (echo the token, store nothing).
        token = _extract_validation(payload) or _extract_validation(dict(request.query_params))
        if token and not any(k in payload for k in ("entity", "resource", "data", "body")):
            return PlainTextResponse(token)

        event = parse_message_event(payload if isinstance(payload, dict) else {"raw": payload})
        event_id = store.add_event(event)
        return {"ok": True, "stored_id": event_id, "category": event.get("category")}

    return app


def run(settings: Optional[Settings] = None) -> int:
    settings = settings or Settings.from_env()
    try:
        import uvicorn
    except ImportError:
        print(
            "The webhook receiver needs the optional extra. Install it with:\n"
            '    pip install "ownerrez-mcp[webhook]"\n'
            "  (or: uvx --from \"ownerrez-mcp[webhook]\" ownerrez-mcp webhook)"
        )
        return 2

    try:
        build_app(settings)  # fail fast with a clear message if FastAPI missing
    except ImportError:
        print('Missing FastAPI. Install with:  pip install "ownerrez-mcp[webhook]"')
        return 2

    print(f"OwnerRez webhook receiver on http://{settings.webhook_host}:{settings.webhook_port}")
    print(f"Storing message events in: {settings.store_path}")
    if settings.webhook_secret:
        print("Shared-secret protection: ON (send X-Webhook-Secret or ?secret=)")
    print("Expose this on a public HTTPS URL and register it with create_webhook_subscription.")
    uvicorn.run(
        build_app(settings),
        host=settings.webhook_host,
        port=settings.webhook_port,
        log_level="info",
    )
    return 0
