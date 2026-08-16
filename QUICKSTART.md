# Quickstart — 2 commands to a working connection

Works on **macOS, Windows, and Linux**, with **any MCP-compatible agent**
(Claude, Cursor, Windsurf, VS Code, Cline, Zed, …). It uses
[uv](https://docs.astral.sh/uv/) so there's no clone and no virtualenv.

## Prerequisite: install `uv` (once)

**macOS / Linux**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell)**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart your terminal afterward so `uvx` is on your `PATH`.

## Before you start (30 seconds)

Grab a **Personal Access Token**: in OwnerRez go to **Settings → API → Personal
Access Tokens**, create one, and copy it. Your username is your OwnerRez login
email.

## Command 1 — set your credentials

**macOS / Linux (bash/zsh)**
```bash
export OWNERREZ_USERNAME="you@example.com"
export OWNERREZ_TOKEN="paste-your-personal-access-token"
```

**Windows (PowerShell)**
```powershell
$env:OWNERREZ_USERNAME = "you@example.com"
$env:OWNERREZ_TOKEN    = "paste-your-personal-access-token"
```

**Windows (Command Prompt)**
```cmd
set OWNERREZ_USERNAME=you@example.com
set OWNERREZ_TOKEN=paste-your-personal-access-token
```

## Command 2 — run it and confirm it works

The same command on every OS:

```bash
uvx --from git+https://github.com/buildwithmanag/ownerrez-mcp ownerrez-mcp probe
```

`uvx` downloads and builds the package into a throwaway environment and runs the
built-in probe, which prints which OwnerRez endpoints your token can reach. Green
`OK 200` lines mean you're connected. 🎉

> Want zero write risk while testing? Set `OWNERREZ_READ_ONLY=1` first
> (`$env:OWNERREZ_READ_ONLY = "1"` on PowerShell) — every write tool (messaging,
> expenses, webhooks) is then hard-blocked.

---

## Connect it to your agent

Almost every MCP client uses the **same config shape** — a server entry with a
`command`, `args`, and `env`. Paste this (edit the two env values), then restart
the app:

```jsonc
{
  "mcpServers": {
    "ownerrez": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/buildwithmanag/ownerrez-mcp", "ownerrez-mcp"],
      "env": {
        "OWNERREZ_USERNAME": "you@example.com",
        "OWNERREZ_TOKEN": "paste-your-personal-access-token"
      }
    }
  }
}
```

### Where each client's config lives

| Agent | Config file / location | Top-level key |
|-------|------------------------|---------------|
| **Claude Desktop / Cowork (macOS)** | `~/Library/Application Support/Claude/claude_desktop_config.json` | `mcpServers` |
| **Claude Desktop / Cowork (Windows)** | `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers` |
| **Cursor** | `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (per project) | `mcpServers` |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | `mcpServers` |
| **Cline (VS Code)** | MCP Servers panel → *Configure* (`cline_mcp_settings.json`) | `mcpServers` |
| **VS Code (Copilot / native MCP)** | `.vscode/mcp.json` (per project) or user settings | `servers` * |
| **Zed** | `settings.json` | `context_servers` * |

\* **VS Code** uses `"servers"` instead of `"mcpServers"` — same inner entry.
**Zed** nests it slightly differently:

```jsonc
// Zed settings.json
{
  "context_servers": {
    "ownerrez": {
      "command": { "path": "uvx", "args": ["--from", "git+https://github.com/buildwithmanag/ownerrez-mcp", "ownerrez-mcp"] },
      "settings": {}
    }
  }
}
```

If your client isn't listed, it almost certainly accepts the standard
`mcpServers` block above — check its "MCP" or "Model Context Protocol" settings.

### Windows note

If your agent reports `uvx` not found, give it the full path instead of just
`uvx`. Find it with `where uvx` (often
`C:\Users\<you>\.local\bin\uvx.exe`) and use that as the `"command"`.

---

## After a PyPI release

Once the package is published to PyPI, the `--from git+…` part goes away
everywhere — the command becomes simply `uvx ownerrez-mcp`, and `args` becomes
`["ownerrez-mcp"]`.

## Next steps

- Prefer OAuth over a token? Run `ownerrez-mcp auth` (see [README](README.md#authentication)).
- Full tool list, safety flags, and config: [README.md](README.md).
- Never commit your token or `.env` — see [SECURITY.md](SECURITY.md).
