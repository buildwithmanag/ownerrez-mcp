# OwnerRez MCP Server — Development Instructions

> **Purpose of this document:** This is the canonical reference for any AI agent
> (Antigravity, Claude, Cursor, etc.) working on this codebase. Read this **before**
> writing or modifying any code. It describes the architecture, conventions,
> module-level internals, data flows, testing strategy, and manual validation
> checklists.

---

## 1. Project Overview

**ownerrez-mcp** is a Python [Model Context Protocol (MCP)](https://modelcontextprotocol.io)
server that bridges the [OwnerRez](https://www.ownerrez.com) vacation-rental
management platform to AI agents (Claude, Cursor, Windsurf, VS Code, Cline, Zed,
etc.). It exposes OwnerRez v2 REST API operations as MCP **tools**, **resources**,
and **prompts** so that an LLM can manage bookings, guests, financials, messaging,
and webhooks in natural language.

| Attribute | Value |
|-----------|-------|
| **Package name** | `ownerrez-mcp` |
| **Current version** | `0.3.0` (bumped in both `pyproject.toml` and `ownerrez_mcp/__init__.py`) |
| **Python support** | 3.10, 3.11, 3.12 |
| **License** | MIT |
| **Build system** | [Hatchling](https://hatch.pypa.io/) |
| **MCP framework** | [FastMCP](https://github.com/jlowin/fastmcp) ≥ 2.0.0 |
| **HTTP client** | [httpx](https://www.python-httpx.org/) ≥ 0.27.0 (synchronous) |
| **Repository** | `github.com/buildwithmanag/ownerrez-mcp` |
| **OwnerRez API docs** | <https://api.ownerrez.com/help/v2> |

### Not affiliated with OwnerRez — this is a community project.

---

## 2. Repository Structure

```
OwnerRezMCP/
├── ownerrez_mcp/               # ← the installable Python package
│   ├── __init__.py             # Version, public exports
│   ├── __main__.py             # `python -m ownerrez_mcp` entry
│   ├── cli.py                  # CLI dispatcher: serve | auth | probe | webhook
│   ├── config.py               # Settings dataclass, env loading
│   ├── client.py               # Synchronous httpx OwnerRez v2 client
│   ├── server.py               # FastMCP server: all tools, resources, prompts
│   ├── auth.py                 # OAuth authorization-code flow helper
│   ├── probe.py                # Live API endpoint prober
│   ├── store.py                # SQLite message store + webhook payload parser
│   └── webhook.py              # FastAPI webhook receiver
├── tests/
│   ├── conftest.py             # Shared pytest fixtures (oauth_settings, pat_settings)
│   ├── test_client.py          # Client auth, pagination, retry, redaction, read-only
│   ├── test_tools.py           # Tool logic via injected FakeClient (no network)
│   ├── test_store.py           # SQLite store CRUD + event parsing
│   └── test_webhook.py         # FastAPI TestClient webhook receiver tests
├── .github/
│   ├── workflows/
│   │   ├── ci.yml              # Lint + test on Python 3.10–3.12
│   │   └── publish.yml         # PyPI Trusted Publishing on version tags
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       └── feature_request.md
├── server.py                   # Backward-compat shim → ownerrez_mcp.server
├── ownerrez_client.py          # Backward-compat shim → ownerrez_mcp.client
├── probe_api.py                # Backward-compat shim → ownerrez_mcp.probe
├── pyproject.toml              # Package metadata, deps, ruff, pytest config
├── requirements.txt            # Flat deps (for pip users who skip pyproject)
├── .env.example                # Annotated env template
├── .gitignore
├── README.md                   # User-facing docs
├── QUICKSTART.md               # Two-command setup for all MCP clients
├── CONTRIBUTING.md             # Dev setup, PR checklist, tool template
├── CHANGELOG.md                # Keep-a-Changelog format, semver
├── RELEASING.md                # PyPI Trusted Publishing + tagging flow
├── SECURITY.md                 # Credential handling policy
└── LICENSE                     # MIT
```

### Root-level shim files

`server.py`, `ownerrez_client.py`, and `probe_api.py` are backward-compatibility
shims from the pre-package era (v0.1.0). They simply re-export from the package.
**Do not add logic to these files.** All new code goes in `ownerrez_mcp/`.

---

## 3. Architecture & Data Flow

```
┌──────────────────┐     stdio (MCP protocol)     ┌──────────────────────┐
│  MCP Client      │◄────────────────────────────►│  ownerrez_mcp/       │
│  (Claude, etc.)  │                               │  server.py (FastMCP) │
└──────────────────┘                               └──────────┬───────────┘
                                                              │
                                                   ┌──────────▼───────────┐
                                                   │  ownerrez_mcp/       │
                                                   │  client.py (httpx)   │
                                                   └──────────┬───────────┘
                                                              │ HTTPS
                                                   ┌──────────▼───────────┐
                                                   │  OwnerRez v2 API     │
                                                   │  api.ownerrez.com/v2 │
                                                   └──────────────────────┘

   Webhook path (optional):

   ┌──────────────────┐    HTTPS POST    ┌─────────────────────┐    SQLite     ┌────────────┐
   │  OwnerRez        │─────────────────►│  ownerrez_mcp/      │──────────────►│ messages.db│
   │  Webhook Events  │                  │  webhook.py (FastAPI)│              └──────┬─────┘
   └──────────────────┘                  └─────────────────────┘                     │
                                                                                     │ read
                                                                              ┌──────▼─────┐
                                                                              │ server.py  │
                                                                              │ inbox tools│
                                                                              └────────────┘
```

### Key architectural decisions

1. **Synchronous client** — `client.py` uses `httpx.Client` (sync), not async. This
   is intentional: FastMCP tools are sync functions, and OwnerRez API latency is
   dominated by network RTT, not concurrency.

2. **Lazy singleton** — `server.py` uses a module-level `_client` singleton
   initialized on first tool call (`def client() -> OwnerRezClient`). Same pattern
   for the `MessageStore`. This avoids failing at import time if credentials aren't
   set (e.g., during tests).

3. **Envelope convention** — Every tool returns `{"ok": True, ...}` on success or
   `{"ok": False, "error": "...", ...}` on failure. Never raises to the MCP layer.

4. **Read-only guard** — Write tools call `_guard_write(action)` which checks
   `SETTINGS.read_only`. The client itself also blocks write HTTP methods when
   `read_only=True`.

5. **Secret redaction** — `client.py` wraps a `_redactor` function that replaces
   any known secret values with `***` in error messages before they reach the user.

---

## 4. Module-by-Module Reference

### 4.1 `config.py` — Settings

A `@dataclass` loaded from environment variables via `Settings.from_env()`.

| Setting | Env Var | Default | Notes |
|---------|---------|---------|-------|
| `base_url` | `OWNERREZ_BASE_URL` | `https://api.ownerrez.com/v2` | Trailing slash stripped |
| `access_token` | `OWNERREZ_ACCESS_TOKEN` | `None` | OAuth Bearer (preferred) |
| `username` | `OWNERREZ_USERNAME` | `None` | PAT Basic auth |
| `token` | `OWNERREZ_TOKEN` | `None` | PAT Basic auth |
| `read_only` | `OWNERREZ_READ_ONLY` | `False` | Truthy = `1, true, yes, on` |
| `max_retries` | `OWNERREZ_MAX_RETRIES` | `3` | Retry count on 429/5xx |
| `timeout` | `OWNERREZ_TIMEOUT` | `30.0` | Seconds |
| `store_path` | `OWNERREZ_STORE` | `~/.ownerrez-mcp/messages.db` | SQLite path |
| `webhook_host` | `OWNERREZ_WEBHOOK_HOST` | `0.0.0.0` | Bind address |
| `webhook_port` | `OWNERREZ_WEBHOOK_PORT` | `8000` | Port |
| `webhook_secret` | `OWNERREZ_WEBHOOK_SECRET` | `None` | Shared secret |
| `client_id` | `OWNERREZ_CLIENT_ID` | `None` | OAuth app |
| `client_secret` | `OWNERREZ_CLIENT_SECRET` | `None` | OAuth app |
| `redirect_uri` | `OWNERREZ_REDIRECT_URI` | `http://localhost:8017/callback` | OAuth callback |
| `authorize_url` | `OWNERREZ_AUTHORIZE_URL` | `https://app.ownerrez.com/oauth/authorize` | OAuth |
| `token_url` | `OWNERREZ_TOKEN_URL` | `https://api.ownerrez.com/oauth/access_token` | OAuth |

**Helper methods:**
- `has_credentials()` — True if OAuth token or username+PAT is set.
- `secrets()` — List of non-None secret strings for redaction.

### 4.2 `client.py` — OwnerRezClient

Synchronous HTTP client wrapping `httpx.Client`.

**Authentication priority:**
1. If `access_token` is set → `Authorization: Bearer {token}`
2. Otherwise → `Authorization: Basic {base64(username:token)}`

**Retry logic (`_send_with_retries`):**
- Retries on HTTP 429 (rate limit) and 5xx (server error).
- Honors `Retry-After` header on 429.
- Exponential backoff: `min(2^attempt, 30)` seconds.
- Max attempts = `max_retries + 1`.
- Network `TransportError` exceptions also trigger retries.

**Pagination (`get_all`):**
- OwnerRez v2 returns `{"items": [...], "next_page_url": "..."}`.
- Follows `next_page_url` links until `null`, empty, or `max_items` reached.
- Also handles bare list responses and single-object responses.
- Default safety cap: 500 items.

**Read-only enforcement:**
- `_request()` raises `ReadOnlyError` for any method in `{POST, PATCH, PUT, DELETE}`
  when `settings.read_only` is `True`.

**Error handling:**
- Parses JSON error bodies, looking for `message` or `error` keys.
- Wraps in `OwnerRezError(status_code, message, url, body)`.
- Redacts secrets from the message.

**Custom exceptions:**
- `OwnerRezError(RuntimeError)` — API error with `status_code`, `url`, `body`.
- `ReadOnlyError(RuntimeError)` — Write blocked by read-only mode.

**Context manager:** Supports `with` statement for automatic `close()`.

### 4.3 `server.py` — MCP Server (The Heart)

Built with `FastMCP`. This is where all MCP tools, resources, and prompts are defined.

#### Tools (16 total)

**Bookings & Stays:**

| Tool | Type | Endpoint | Notes |
|------|------|----------|-------|
| `list_bookings` | READ | `GET /bookings` | Bounded by `since_utc` (default: 180 days ago). Optional client-side `arrival_start`/`arrival_end` filtering. |
| `get_booking` | READ | `GET /bookings/{id}` | Single booking by ID. |
| `who_is_staying` | READ | derived | Fetches all properties + bookings from last year, filters where `arrival <= date < departure`. |

**Reference Lookups:**

| Tool | Type | Endpoint |
|------|------|----------|
| `list_properties` | READ | `GET /properties` |
| `list_owners` | READ | `GET /owners` |
| `find_guest` | READ | `GET /guests` (bounded by `created_since_utc`, default 2015-01-01) |

**Financials (read-only):**

| Tool | Type | Endpoint |
|------|------|----------|
| `list_quotes` | READ | `GET /quotes` |
| `list_payments` | READ | `GET /payments` |
| `list_refunds` | READ | `GET /refunds` |
| `list_fees` | READ | `GET /fees` |

**Messaging:**

| Tool | Type | Endpoint | Notes |
|------|------|----------|-------|
| `list_messages` | READ | `GET /messages` | Requires `threadId` (camelCase). |
| `send_message` | WRITE | `POST /messages` | Guarded by `_guard_write`. Uses camelCase `threadId`. |

**Webhooks:**

| Tool | Type | Endpoint |
|------|------|----------|
| `list_webhook_subscriptions` | READ | `GET /webhooksubscriptions` |
| `create_webhook_subscription` | WRITE | `POST /webhooksubscriptions` |
| `delete_webhook_subscription` | WRITE | `DELETE /webhooksubscriptions/{id}` |

**Inbox (local store, no API calls):**

| Tool | Type | Data Source |
|------|------|-------------|
| `list_open_messages` | READ | SQLite (unhandled incoming messages) |
| `get_message_event` | READ | SQLite (single event by ID) |
| `mark_message_handled` | LOCAL WRITE | SQLite (toggle `handled` flag) |

> **Critical OwnerRez API limitations:**
> - There is **no public expense-creation endpoint** (confirmed 404).
> - There is **no endpoint that lists all message threads**. You must learn
>   `threadId` from a webhook event.
> - Bookings are bounded by `since_utc` (changed-since), not arrival dates.
> - Guests are bounded by `created_since_utc`.

#### Resources (2)

| URI | Returns |
|-----|---------|
| `ownerrez://properties` | All properties via `GET /properties` |
| `ownerrez://owners` | All owners via `GET /owners` |

#### Prompts (2)

| Prompt | Purpose |
|--------|---------|
| `draft_checkin_message(guest_name, property_name, arrival)` | Generate a warm check-in message (< 120 words) |
| `draft_guest_reply(guest_message, tone)` | Draft a reply to an incoming guest message |

#### Internal helpers

- `client()` — Lazy singleton for `OwnerRezClient`.
- `store()` — Lazy singleton for `MessageStore`.
- `_today()` — Today's date as `YYYY-MM-DD`.
- `_utc_days_ago(days)` — UTC timestamp N days ago as ISO-8601.
- `_err(exc)` — Converts exceptions to `{"ok": False, ...}` envelope.
- `_guard_write(action)` — Returns error dict if read-only, else `None`.

### 4.4 `cli.py` — Command-Line Interface

Entry point: `ownerrez-mcp` (registered via `[project.scripts]` in `pyproject.toml`).

| Subcommand | Action | Module |
|------------|--------|--------|
| `serve` (default) | Runs MCP server over stdio | `server.run()` |
| `auth` | OAuth authorization-code flow | `auth.run_oauth_flow()` |
| `probe` | Tests live API connectivity | `probe.main()` |
| `webhook` | Runs FastAPI webhook receiver | `webhook.run()` |
| `--version` | Print version | — |
| `-h, --help` | Print help | — |

Also runnable as `python -m ownerrez_mcp` via `__main__.py`.

### 4.5 `auth.py` — OAuth Flow

Implements the OAuth 2.0 authorization code grant:

1. Starts a local HTTP server on the redirect URI port (default 8017).
2. Opens the OwnerRez authorize URL in the browser with a random `state` param.
3. Waits for the callback (up to 300s timeout).
4. Validates `state` matches, exchanges the code for an access token.
5. Prints `OWNERREZ_ACCESS_TOKEN=<token>` to stdout.

**Requires:** `OWNERREZ_CLIENT_ID` + `OWNERREZ_CLIENT_SECRET` (from an OAuth app
created in OwnerRez → Settings → API → OAuth Apps).

### 4.6 `probe.py` — API Prober

Read-only utility that tests which API endpoints the current credentials can reach.

Probes these endpoints:
- `GET /bookings` (with `since_utc`)
- `GET /properties`
- `GET /owners`
- `GET /guests` (with `created_since_utc`)
- `GET /quotes`
- `GET /payments`
- `GET /webhooksubscriptions`

Prints `OK 200` or `ERR {status}` for each. Does not probe messaging (requires
`threadId`) or expenses (no public endpoint).

### 4.7 `store.py` — Message Store

SQLite-based local store for inbound webhook message events. Pure stdlib (no
extra dependencies).

**Schema:**
```sql
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
```

**Key methods:**
- `add_event(event)` → Insert a parsed event, returns row ID.
- `list_open(limit)` → Unhandled inbound messages, newest first.
- `get(event_id)` → Single event by ID.
- `mark_handled(event_id, handled)` → Toggle handled flag.
- `counts()` → `{"total": N, "open": N}`.

**Payload parser (`parse_message_event`):**
Best-effort extraction from OwnerRez webhook payloads. Handles multiple possible
field names (e.g., `threadId` / `thread_id` / `conversation_id`). Always preserves
the raw payload.

### 4.8 `webhook.py` — Webhook Receiver

FastAPI app that receives OwnerRez webhook POST events.

**Optional extra:** Requires `pip install "ownerrez-mcp[webhook]"` (adds `fastapi`
+ `uvicorn`).

**Endpoints:**
- `GET /` — Health check + subscription validation (echoes `validationToken`).
- `POST /` — Receives events, parses them, stores in SQLite.

**Security:**
- Optional `OWNERREZ_WEBHOOK_SECRET` — must match `X-Webhook-Secret` header or
  `?secret=` query param. Rejects 401 if missing.

**Validation handshake:**
- Recognizes `validationToken`, `validation_token`, `challenge`, `validation` keys.
- Echoes the token back as plain text (some providers require this).

> **Important:** The webhook receiver does NOT have `from __future__ import
> annotations` — this is intentional. FastAPI needs real type annotations for
> route parameter injection, not stringized forward-refs.

---

## 5. Authentication Methods

### Method A: Personal Access Token (simplest)

1. In OwnerRez: **Settings → API → Personal Access Tokens** → Create one.
2. Set environment variables:
   ```bash
   export OWNERREZ_USERNAME="you@example.com"
   export OWNERREZ_TOKEN="your_personal_access_token"
   ```
3. The client sends `Authorization: Basic {base64(username:token)}`.

### Method B: OAuth (multi-account / distribution)

1. In OwnerRez: **Settings → API → OAuth Apps** → Create an app.
2. Set `OWNERREZ_CLIENT_ID` and `OWNERREZ_CLIENT_SECRET`.
3. Run `ownerrez-mcp auth` → opens browser → captures callback → prints token.
4. Set `OWNERREZ_ACCESS_TOKEN` with the printed value.
5. The client sends `Authorization: Bearer {token}`.

**Priority:** If both `OWNERREZ_ACCESS_TOKEN` and `OWNERREZ_USERNAME`/`TOKEN` are
set, OAuth (Bearer) takes precedence.

---

## 6. Conventions & Coding Standards

### 6.1 Return envelope

**Every MCP tool** must return a dict with:
- Success: `{"ok": True, "count": N, "<entity>": [...]}` (or similar)
- Failure: `{"ok": False, "error": "...", ...}` (may include `status_code`, `details`, `read_only`)

**Never raise exceptions from a tool.** Catch with `except Exception as exc: # noqa: BLE001`
and return `_err(exc)`.

### 6.2 Adding a new tool

1. Add the function in `server.py` with `@mcp.tool` decorator.
2. Write a clear one-line docstring — the LLM reads it as the tool description.
3. Longer args docs use Google-style docstrings in the function body.
4. Guard writes with `_guard_write("description of action")`.
5. Use `client()` (lazy singleton), not a direct import.
6. Follow the `try/except → _err(exc)` pattern.
7. Add a test in `tests/test_tools.py` using the `FakeClient` injection pattern.
8. Update `README.md` tool table and `CHANGELOG.md` under "Unreleased".

Template:
```python
@mcp.tool
def my_tool(some_id: int) -> Dict[str, Any]:
    """Short description the model will read."""
    try:
        return {"ok": True, "data": client().get(f"/some/{some_id}")}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
```

### 6.3 Linting & formatting

- **Ruff** for linting and formatting.
- `line-length = 100`, `target-version = "py310"`.
- Selected rules: `E` (pycodestyle), `F` (pyflakes), `I` (isort).
- `E501` (line length) is ignored (Ruff enforces its own).
- Run: `ruff check .`

### 6.4 Version bumping

Version must be kept in sync in **two places**:
1. `pyproject.toml` → `[project] version`
2. `ownerrez_mcp/__init__.py` → `__version__`

### 6.5 Commit messages

Conventional-ish format appreciated but not required.

### 6.6 Changelog

Follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Update
under "Unreleased" for user-facing changes.

### 6.7 OwnerRez API field naming

- The OwnerRez v2 API uses **camelCase** for some fields (e.g., `threadId`,
  `next_page_url`). When constructing payloads, match the API exactly.
- Query parameters: `since_utc`, `created_since_utc`, `property_ids`, `include_guest`.
- Body fields: `threadId` (camelCase), `body`, `attachment_url`.

---

## 7. Dependencies

### Core (always installed)

| Package | Min Version | Purpose |
|---------|-------------|---------|
| `fastmcp` | ≥ 2.0.0 | MCP server framework |
| `httpx` | ≥ 0.27.0 | HTTP client (sync) |
| `python-dotenv` | ≥ 1.0.0 | `.env` file loading |

### Optional extras

**`[webhook]`** — For the inbound-message webhook receiver:
| Package | Min Version | Purpose |
|---------|-------------|---------|
| `fastapi` | ≥ 0.110 | Web framework for webhook endpoint |
| `uvicorn` | ≥ 0.29 | ASGI server |

**`[dev]`** — For development:
| Package | Min Version | Purpose |
|---------|-------------|---------|
| `pytest` | ≥ 8.0 | Test runner |
| `respx` | ≥ 0.21 | Mock httpx requests |
| `ruff` | ≥ 0.6 | Linter / formatter |
| `fastapi` | ≥ 0.110 | Needed for webhook tests |
| `uvicorn` | ≥ 0.29 | Needed for webhook tests |
| `httpx` | ≥ 0.27.0 | (already a core dep, listed for completeness) |

### Stdlib dependencies (no install needed)

- `sqlite3` — Message store
- `http.server` — OAuth callback listener
- `webbrowser` — Open authorize URL
- `argparse` — Probe CLI
- `base64`, `secrets`, `json`, `os`, `time`, `datetime`, `urllib.parse`

---

## 8. Testing

### 8.1 Running tests

```bash
# Install dev deps
pip install -e ".[dev]"

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_client.py

# Run a specific test
pytest tests/test_client.py::test_bearer_auth_header
```

### 8.2 Test architecture

Tests use **no real network calls**. Two mocking strategies:

1. **`respx`** (in `test_client.py`) — Mocks `httpx` at the transport level.
   Used for testing the HTTP client's auth headers, pagination, retry logic,
   error redaction, and read-only enforcement.

2. **`FakeClient`** (in `test_tools.py`) — A simple in-memory fake that replaces
   the `client()` singleton via `monkeypatch`. Used for testing tool business
   logic without any HTTP layer.

3. **`FastAPI TestClient`** (in `test_webhook.py`) — Uses FastAPI's built-in test
   client against the webhook app. Tests event storage, health endpoint,
   validation handshake, and secret enforcement.

4. **`tmp_path`** (in `test_store.py`, `test_webhook.py`) — pytest's built-in
   temp directory fixture for isolated SQLite databases.

### 8.3 Test fixtures (`conftest.py`)

```python
@pytest.fixture
def oauth_settings():
    return Settings(access_token="SECRET-OAUTH-TOKEN", max_retries=2, timeout=5.0)

@pytest.fixture
def pat_settings():
    return Settings(username="me@example.com", token="SECRET-PAT", max_retries=2, timeout=5.0)
```

### 8.4 Existing test coverage

| File | What it tests |
|------|---------------|
| `test_client.py` | Bearer auth header, Basic auth header, missing credentials raise, pagination follow, secret redaction in errors, retry on 429, read-only blocks writes |
| `test_tools.py` | `who_is_staying` date filtering, `send_message` success + payload shape, `send_message` blocked in read-only, `create_webhook_subscription` blocked in read-only |
| `test_store.py` | Add/list/mark_handled lifecycle, outbound not listed as open, `parse_message_event` field extraction |
| `test_webhook.py` | POST stores event, GET health + challenge echo, shared secret enforcement |

### 8.5 CI pipeline (`.github/workflows/ci.yml`)

- Triggers on: push to `main`, any pull request.
- Matrix: Python 3.10, 3.11, 3.12 on `ubuntu-latest`.
- Steps: install `.[dev]` → `ruff check .` → `pytest`.
- `fail-fast: false` — all matrix versions run even if one fails.

### 8.6 What is NOT tested (gaps)

- `auth.py` OAuth flow (would need browser/HTTP server mocking).
- `probe.py` output format.
- `cli.py` dispatch logic and `--help`/`--version` flags.
- `list_bookings` arrival filtering logic (client-side date filtering).
- Individual financial tools (`list_quotes`, `list_payments`, `list_refunds`, `list_fees`).
- Error envelope structure for different exception types.
- `get_all` edge cases: bare list responses, single-object responses.
- Pagination `max_items` cap enforcement.

---

## 9. Manual Testing & Validation Checklist

### 9.1 Prerequisites

- [ ] OwnerRez account with API access.
- [ ] Personal Access Token created (Settings → API → Personal Access Tokens).
- [ ] Python 3.10+ installed.
- [ ] `uv` installed (for `uvx` testing).

### 9.2 Installation validation

```bash
# From source
git clone https://github.com/buildwithmanag/ownerrez-mcp
cd ownerrez-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

- [ ] `pip install -e ".[dev]"` completes without errors.
- [ ] `ownerrez-mcp --version` prints `ownerrez-mcp 0.3.0`.
- [ ] `ownerrez-mcp --help` prints the help text with all 4 subcommands.
- [ ] `python -m ownerrez_mcp --help` also works.

### 9.3 Lint & test validation

```bash
ruff check .
pytest -v
```

- [ ] `ruff check .` reports no errors.
- [ ] `pytest` passes all tests (currently 11 tests across 4 files).

### 9.4 API probe (live, read-only, safe)

```bash
export OWNERREZ_USERNAME="you@example.com"
export OWNERREZ_TOKEN="your_pat"
ownerrez-mcp probe
```

- [ ] Output shows `OK 200` for: bookings, properties, owners, guests, quotes, payments, webhooksubscriptions.
- [ ] No credentials appear in the output.
- [ ] Output includes the base URL and read-only status.

### 9.5 MCP server smoke test

```bash
# Run the server (it communicates over stdio)
ownerrez-mcp serve
# Or: ownerrez-mcp (serve is the default)
```

- [ ] Server starts without error (you'll see it waiting for MCP input on stdin).
- [ ] Ctrl+C exits cleanly.

### 9.6 MCP client integration test

Add to your MCP client config (e.g., Claude Desktop):
```jsonc
{
  "mcpServers": {
    "ownerrez": {
      "command": "/path/to/.venv/bin/ownerrez-mcp",
      "env": {
        "OWNERREZ_USERNAME": "you@example.com",
        "OWNERREZ_TOKEN": "your_pat"
      }
    }
  }
}
```

- [ ] Client discovers the OwnerRez tools (should show 16 tools).
- [ ] `list_properties` returns `{"ok": true, "count": N, "properties": [...]}`.
- [ ] `list_bookings` returns bookings with `arrival`, `departure`, `guest` fields.
- [ ] `who_is_staying` returns currently in-house guests (or empty list).
- [ ] `find_guest` with a query returns matching guests.
- [ ] Financial tools (`list_quotes`, `list_payments`, `list_refunds`, `list_fees`) return data.
- [ ] `list_webhook_subscriptions` returns current subscriptions.
- [ ] Resources `ownerrez://properties` and `ownerrez://owners` are browsable.
- [ ] Prompts `draft_checkin_message` and `draft_guest_reply` appear.

### 9.7 Read-only mode validation

```bash
export OWNERREZ_READ_ONLY=1
ownerrez-mcp probe
```

Test via MCP client:
- [ ] `send_message(thread_id=X, body="test")` returns `{"ok": false, "read_only": true, ...}`.
- [ ] `create_webhook_subscription(url="...", category="message")` returns read-only error.
- [ ] `delete_webhook_subscription(subscription_id=X)` returns read-only error.
- [ ] All read tools still work normally.

### 9.8 Write tool validation (USE WITH CAUTION)

> ⚠️ These tests modify live data. Use a test/staging account if possible.

- [ ] `send_message(thread_id=<known>, body="Test from MCP")` sends successfully.
- [ ] `create_webhook_subscription(url="https://...", category="message")` creates a subscription.
- [ ] `delete_webhook_subscription(subscription_id=<created_id>)` removes it.

### 9.9 Webhook receiver validation

```bash
pip install "ownerrez-mcp[webhook]"
ownerrez-mcp webhook
```

- [ ] Server starts, prints bind address and store path.
- [ ] `GET /` returns `{"ok": true, "service": "ownerrez-webhook", ...}`.
- [ ] `GET /?validationToken=abc123` returns plain text `abc123`.
- [ ] `POST /` with a message payload stores the event.
- [ ] Via MCP client: `list_open_messages` shows the stored event.
- [ ] `mark_message_handled(event_id=N)` clears it from the open list.

**With shared secret:**
```bash
export OWNERREZ_WEBHOOK_SECRET="my-secret"
ownerrez-mcp webhook
```

- [ ] `POST /` without `X-Webhook-Secret` header returns 401.
- [ ] `POST /` with correct `X-Webhook-Secret: my-secret` header stores event.
- [ ] `POST /?secret=my-secret` also works.

### 9.10 OAuth flow validation

```bash
export OWNERREZ_CLIENT_ID="your_client_id"
export OWNERREZ_CLIENT_SECRET="your_client_secret"
ownerrez-mcp auth
```

- [ ] Opens browser to OwnerRez authorize page.
- [ ] After authorizing, callback is captured.
- [ ] Prints `OWNERREZ_ACCESS_TOKEN=<token>`.
- [ ] Token works when used with `OWNERREZ_ACCESS_TOKEN`.

### 9.11 uvx / remote install validation

```bash
export OWNERREZ_USERNAME="you@example.com"
export OWNERREZ_TOKEN="your_pat"
uvx --from git+https://github.com/buildwithmanag/ownerrez-mcp ownerrez-mcp probe
```

- [ ] Downloads, builds, and runs without errors.
- [ ] Probe output shows `OK 200` for accessible endpoints.

### 9.12 Error handling validation

- [ ] With **no credentials** set: `ownerrez-mcp probe` fails with a clear message
      about missing credentials.
- [ ] With **invalid credentials**: probe shows `ERR 401` for each endpoint. No
      secrets in error messages.
- [ ] With **wrong base URL**: appropriate connection error.

---

## 10. CI/CD & Release Process

### 10.1 CI (`.github/workflows/ci.yml`)

Automatic on every push to `main` and every PR. Runs lint + test on Python 3.10–3.12.

### 10.2 Publishing (`.github/workflows/publish.yml`)

Triggered by pushing a tag matching `v*` (e.g., `v0.3.0`).

**Flow:**
1. **build** job: Verify tag matches `pyproject.toml` version → build sdist + wheel → `twine check`.
2. **publish** job: Push to PyPI via Trusted Publishing (OIDC, no API tokens).
3. **github-release** job: Create GitHub Release with auto-generated notes + built artifacts.

**One-time setup required:**
1. Reserve name on PyPI.
2. Add Trusted Publisher on PyPI (owner: `buildwithmanag`, repo: `ownerrez-mcp`, workflow: `publish.yml`, environment: `pypi`).
3. Create `pypi` GitHub environment.

### 10.3 Release checklist

1. Bump version in `pyproject.toml` and `ownerrez_mcp/__init__.py`.
2. Update `CHANGELOG.md`.
3. `git commit -am "Release vX.Y.Z"`
4. `git tag vX.Y.Z`
5. `git push origin main --tags`

---

## 11. Known OwnerRez API Limitations

These were discovered through live API testing and are baked into the server design:

1. **No expense creation endpoint** — `POST /expenses` returns 404. The tools
   `add_expense_for_booking`, `_property`, and `_owner` were removed in v0.2.1.

2. **No thread listing endpoint** — There is no `GET /threads` or similar. You
   cannot enumerate all message conversations. Thread IDs (`threadId`) are learned
   from booking data or webhook events.

3. **Bookings are time-bounded** — `GET /bookings` requires `since_utc` (changed-since
   timestamp), not arrival dates. Client-side filtering is used for arrival windows.

4. **Guests are time-bounded** — `GET /guests` requires `created_since_utc`.

5. **Messaging uses camelCase** — The `threadId` field is camelCase in both
   query params and POST bodies, despite some other fields being snake_case.

---

## 12. Security Considerations

1. **Never commit `.env`** — It's in `.gitignore`.
2. **Secret redaction** — The client replaces known secret values with `***` in
   all error output.
3. **Read-only mode** — `OWNERREZ_READ_ONLY=1` hard-blocks all write operations
   at both the tool level and the HTTP client level.
4. **Webhook secret** — Optional shared secret for the webhook receiver; always
   run behind HTTPS in production.
5. **Prefer scoped tokens** — Use the most restrictive credentials possible.
6. **Transport** — The server only communicates with `https://api.ownerrez.com`.

---

## 13. Development Workflow

### Quick start for a new developer

```bash
git clone https://github.com/buildwithmanag/ownerrez-mcp
cd ownerrez-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env     # fill in credentials
ruff check .             # lint
pytest                   # test
ownerrez-mcp probe       # verify API connectivity
```

### Day-to-day workflow

1. Create a feature branch.
2. Write code in `ownerrez_mcp/`.
3. Add tests in `tests/`.
4. Run `ruff check .` and `pytest`.
5. Update `CHANGELOG.md` under "Unreleased".
6. Open a PR.

### Adding a new OwnerRez API integration

1. Check [OwnerRez API docs](https://api.ownerrez.com/help/v2) for the endpoint.
2. Test with `ownerrez-mcp probe` or a quick manual `httpx` call to confirm it works.
3. Add the tool in `server.py` following the template in section 6.2.
4. Add tests using `FakeClient` in `test_tools.py`.
5. If the endpoint is new and undocumented, note it in the "Known Limitations" section.
6. Update the README tool table.

---

## 14. Glossary

| Term | Meaning |
|------|---------|
| **MCP** | Model Context Protocol — open standard for connecting LLMs to external tools |
| **FastMCP** | Python library for building MCP servers |
| **PAT** | Personal Access Token (OwnerRez HTTP Basic auth) |
| **Tool** | An MCP function the LLM can call |
| **Resource** | An MCP browsable data endpoint |
| **Prompt** | An MCP template for generating LLM prompts |
| **uvx** | `uv`'s tool runner (like `npx` for Python) |
| **respx** | Mock library for httpx |
| **Hatchling** | Python build backend (PEP 517) |
| **Ruff** | Extremely fast Python linter/formatter written in Rust |
| **Trusted Publishing** | PyPI's OIDC-based publish (no API tokens) |
