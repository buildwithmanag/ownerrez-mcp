# Security Policy

## Reporting a vulnerability

Please report security issues privately by opening a
[GitHub security advisory](https://github.com/buildwithmanag/ownerrez-mcp/security/advisories/new)
rather than a public issue. We'll respond as quickly as we can.

## Handling credentials

- **Never commit your `.env`** or paste tokens into issues/PRs. `.env` is
  gitignored by default.
- Prefer a **Personal Access Token** scoped to only what you need, or an OAuth
  token you can revoke.
- The server **redacts known secrets** from error messages, but treat all logs
  as sensitive anyway.
- Run with `OWNERREZ_READ_ONLY=1` when you only need read access — it hard-blocks
  every write tool (messaging, expenses, webhook changes).
- This server talks only to `https://api.ownerrez.com`. Keep transport on HTTPS.
