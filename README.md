# OwnerRez MCP Server

[![CI](https://github.com/buildwithmanag/ownerrez-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/buildwithmanag/ownerrez-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

A [Model Context Protocol](https://modelcontextprotocol.io) server that connects
[OwnerRez](https://www.ownerrez.com) to Claude (Cowork / Claude Desktop) and any
other MCP client. Ask about bookings, see who's checked in, message guests,
record expenses, and manage webhooks — in natural language. Built with Python +
[FastMCP](https://github.com/jlowin/fastmcp).

> ⚠️ Community project, not affiliated with OwnerRez.

## Quickstart

**New here? [QUICKSTART.md](QUICKSTART.md) gets you to a working connection in two commands.**

The fastest path — no clone, no venv — using [uv](https://docs.astral.sh/uv/):

This same server works in **any MCP client** — Claude, Cursor, Windsurf, VS Code,
Cline, Zed, and more. Add the standard block below to your client's MCP config
([QUICKSTART.md](QUICKSTART.md) lists each client's config file location and the
few that use a different key):

```jsonc
{
  "mcpServers": {
    "ownerrez": {
      "command": "uvx",
      // Before a PyPI release, run straight from GitHub:
      "args": ["--from", "git+https://github.com/buildwithmanag/ownerrez-mcp", "ownerrez-mcp"],
      // After `pip`/PyPI publish this becomes simply: "args": ["ownerrez-mcp"],
      "env": {
        "OWNERREZ_USERNAME": "you@example.com",
        "OWNERREZ_TOKEN": "your_personal_access_token"
      }
    }
  }
}
```

Restart your client and the OwnerRez tools appear. That's it.

Prefer to run from source? See [Install from source](#install-from-source).

## What it can do

**Tools**

| Tool | Purpose | Endpoint |
|------|---------|----------|
| `list_bookings` | Current & upcoming bookings by date / property | `GET /v2/bookings` ✅ |
| `get_booking` | Full detail for one booking | `GET /v2/bookings/{id}` ✅ |
| `who_is_staying` | Who's checked in right now, per property | derived ✅ |
| `list_properties` / `list_owners` / `find_guest` | Reference lookups | `GET` ✅ |
| `list_quotes` / `list_payments` / `list_refunds` / `list_fees` | Financial reads | `GET` ✅ |
| `find_open_messages` | Recent / open guest message threads | `GET /v2/threads` ⚠️ |
| `list_messages` | Messages within a thread | `GET /v2/messages` ✅ |
| `send_message` | Reply to a guest *(write)* | `POST /v2/messages` ✅ |
| `add_expense_for_booking` / `_property` / `_owner` | Record an expense *(write)* | `POST /v2/expenses` ⚠️ |
| `list_webhook_subscriptions` | List webhooks | `GET` ✅ |
| `create_webhook_subscription` / `delete_webhook_subscription` | Manage webhooks *(write)* | `POST`/`DELETE` ✅ |

**Resources:** `ownerrez://properties`, `ownerrez://owners`
**Prompts:** `draft_checkin_message`, `draft_guest_reply`

⚠️ Two endpoints aren't fully documented publicly — **expense creation** and
**message-thread listing**. Run the [probe](#verify-against-the-live-api) to
confirm what your account supports; the tools degrade gracefully with a clear
message if an endpoint isn't available.

### Example prompts

- "Who's checking in this weekend?"
- "Who's currently staying at the Beach House?"
- "Draft a check-in message for the guest arriving tomorrow at Cabin 3."
- "Show me all payments on booking 84213."
- "Add a $120 cleaning expense to booking 84213."
- "Any guest messages I haven't replied to?"

## Authentication

Pick whichever fits — the server prefers OAuth if both are set.

**Personal Access Token (simplest for one account).** OwnerRez → Settings → API
→ Personal Access Tokens. Set `OWNERREZ_USERNAME` + `OWNERREZ_TOKEN`.

**OAuth (for multi-account / distribution).** Create an OAuth app in OwnerRez,
set `OWNERREZ_CLIENT_ID` + `OWNERREZ_CLIENT_SECRET`, then run the built-in helper:

```bash
ownerrez-mcp auth
```

It opens the authorize page, captures the redirect locally, and prints the
`OWNERREZ_ACCESS_TOKEN` to save.

## Safety: read-only mode

Set `OWNERREZ_READ_ONLY=1` to hard-block every write tool (messaging, expenses,
webhook changes). Great for letting an assistant explore your data without any
risk of it messaging a guest or mutating records.

## Verify against the live API

```bash
ownerrez-mcp probe                 # read-only checks (safe)
ownerrez-mcp probe --probe-writes  # also tests the expense POST endpoint with
                                   # an invalid body (creates nothing)
```

The output tells you exactly which endpoints your token can reach and whether
expense creation is `WRITABLE` or `NOT SUPPORTED`.

## Install from source

```bash
git clone https://github.com/buildwithmanag/ownerrez-mcp
cd ownerrez-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in your credentials
ownerrez-mcp probe     # sanity-check connectivity
```

Point your MCP client at the venv's executable:

```jsonc
{
  "mcpServers": {
    "ownerrez": {
      "command": "/path/to/ownerrez-mcp/.venv/bin/ownerrez-mcp",
      "env": { "OWNERREZ_ACCESS_TOKEN": "..." }
    }
  }
}
```

## Configuration reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `OWNERREZ_ACCESS_TOKEN` | — | OAuth access token (preferred) |
| `OWNERREZ_USERNAME` / `OWNERREZ_TOKEN` | — | Personal Access Token (Basic auth) |
| `OWNERREZ_READ_ONLY` | `0` | Block all write tools when truthy |
| `OWNERREZ_MAX_RETRIES` | `3` | Retries on 429/5xx |
| `OWNERREZ_TIMEOUT` | `30` | Request timeout (seconds) |
| `OWNERREZ_BASE_URL` | `https://api.ownerrez.com/v2` | API base URL |
| `OWNERREZ_CLIENT_ID` / `OWNERREZ_CLIENT_SECRET` | — | OAuth app creds (for `auth`) |

## Development

```bash
ruff check .   # lint
pytest         # tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Every tool returns a structured
`{"ok": ...}` envelope, follows OwnerRez v2 pagination, redacts secrets from
errors, and retries transient failures.

## License

MIT — see [LICENSE](LICENSE). API reference: <https://api.ownerrez.com/help/v2>
