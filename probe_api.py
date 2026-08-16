"""Backward-compatible shim for the API probe.

Prefer:  ``ownerrez-mcp probe``  (or ``python -m ownerrez_mcp probe``).
"""

from ownerrez_mcp.probe import main

if __name__ == "__main__":
    raise SystemExit(main())
