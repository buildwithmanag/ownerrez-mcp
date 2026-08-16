# Contributing

Thanks for helping improve the OwnerRez MCP server!

## Dev setup

```bash
git clone https://github.com/buildwithmanag/ownerrez-mcp
cd ownerrez-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Before you open a PR

```bash
ruff check .     # lint
pytest           # tests
```

CI runs both across Python 3.10–3.12; please keep them green and add tests for
new behavior.

## Adding a tool

Tools live in `ownerrez_mcp/server.py`. Keep the return envelope consistent
(`{"ok": True, ...}` / `{"ok": False, "error": ...}`), guard any write with
`_guard_write(...)`, and give the function a clear one-line docstring — the
model reads it as the tool description.

```python
@mcp.tool
def my_tool(some_id: int) -> dict:
    """Short description the model will read."""
    try:
        return {"ok": True, "data": client().get(f"/some/{some_id}")}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
```

## Verifying against the live API

Endpoints that aren't fully documented (expenses write, message threads) should
be confirmed with `ownerrez-mcp probe` before you rely on them. Never paste real
tokens or account data into issues or PRs.

## Conventions

- Ruff for lint/format (`line-length = 100`).
- Conventional-ish commit messages appreciated but not required.
- Update `CHANGELOG.md` under "Unreleased" for user-facing changes.
