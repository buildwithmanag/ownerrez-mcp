# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
