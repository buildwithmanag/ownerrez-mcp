# Releasing

This project publishes to [PyPI](https://pypi.org/) automatically when you push
a version tag. It uses **PyPI Trusted Publishing** (OpenID Connect), so there are
**no API tokens** to create or store as secrets.

## One-time setup

1. **Reserve the name on PyPI.** Sign in at <https://pypi.org>. The project name
   is `ownerrez-mcp` (from `pyproject.toml`).

2. **Add a Trusted Publisher.** On PyPI go to your project (or, for the very
   first release, use *Publishing → Add a pending publisher*) and add a GitHub
   publisher with:
   - **Owner:** `buildwithmanag`
   - **Repository:** `ownerrez-mcp`
   - **Workflow name:** `publish.yml`
   - **Environment:** `pypi`

3. **Create the GitHub environment.** In the repo: *Settings → Environments →
   New environment* named **`pypi`**. (Optionally add a required reviewer so
   every publish needs a click of approval.)

That's it — no secrets to manage.

## Cut a release

1. Bump the version in **both** places (keep them in sync):
   - `pyproject.toml` → `[project] version`
   - `ownerrez_mcp/__init__.py` → `__version__`

2. Update `CHANGELOG.md`.

3. Commit, tag, and push the tag:

   ```bash
   git commit -am "Release v0.2.1"
   git tag v0.2.1
   git push origin main --tags
   ```

The **Publish to PyPI** workflow then:
- verifies the tag matches the `pyproject` version (fails fast on a mismatch),
- builds the sdist + wheel and runs `twine check`,
- publishes to PyPI via Trusted Publishing,
- creates a GitHub Release with auto-generated notes and the built artifacts.

## After the first successful publish

Installation collapses to the short form everywhere — no `--from` needed:

```bash
uvx ownerrez-mcp
```

and MCP client configs become:

```jsonc
{ "mcpServers": { "ownerrez": { "command": "uvx", "args": ["ownerrez-mcp"], "env": { } } } }
```

Update `README.md` / `QUICKSTART.md` to drop the `git+https://…` form when you're
ready.
