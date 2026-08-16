# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-08-16

### Added
- **Inbound-message webhook receiver** (`ownerrez-mcp webhook`, optional
  `[webhook]` extra): a small FastAPI service that captures OwnerRez `message`
  webhook events into a local SQLite store, with subscription-validation and an
  optional shared secret.
- **Inbox tools** backed by that store: `list_open_messages`,
  `get_message_event`, `mark_message_handled` — a real "open messages" inbox
  (works even in read-only mode; they touch local state only).
- Config: `OWNERREZ_STORE`, `OWNERREZ_WEBHOOK_HOST`, `OWNERREZ_WEBHOOK_PORT`,
  `OWNERREZ_WEBHOOK_SECRET`.

## [0.2.1] - 2026-08-16

### Fixed (verified against the live OwnerRez v2 API)
- `list_bookings` / `who_is_staying`: use `since_utc` (+ `status`) instead of the
  non-existent `from`/`to` params; added optional client-side arrival filtering.
- `find_guest`: use `created_since_utc` (the endpoint requires a "since" bound).
- Messaging: use camelCase `threadId` for `GET`/`POST /v2/messages`.

### Removed
- `find_open_messages` — OwnerRez has no thread-listing endpoint; inbound
  messages are delivered via `message` webhooks instead.
- `add_expense_for_booking` / `_property` / `_owner` — OwnerRez v2 exposes no
  public expense-creation endpoint (confirmed 404).

## [0.2.0] - 2026-08-16

### Added
- Installable package with a `ownerrez-mcp` console entry point (`uvx`/`pipx` ready).
- Subcommands: `ownerrez-mcp serve | auth | probe`.
- OAuth authorization-code helper (`ownerrez-mcp auth`) alongside Personal Access Token auth.
- Read-only mode via `OWNERREZ_READ_ONLY` that hard-blocks all write tools.
- Automatic retries with backoff on 429 (honoring `Retry-After`) and 5xx.
- Secret redaction in error output.
- MCP resources (`ownerrez://properties`, `ownerrez://owners`) and message-draft prompts.
- Read tools for quotes, payments, refunds, and fees.
- Unit tests (pytest + respx) and GitHub Actions CI.

## [0.1.0]

### Added
- Initial server: bookings, in-house guests, messaging, expenses, webhooks.
