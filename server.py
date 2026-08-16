"""Backward-compatible entry point.

The server now lives in the ``ownerrez_mcp`` package. This shim keeps the old
``python server.py`` launch command working. Prefer the installed console
script instead:  ``ownerrez-mcp``  (or ``python -m ownerrez_mcp``).
"""

from ownerrez_mcp.server import mcp, run

__all__ = ["mcp", "run"]

if __name__ == "__main__":
    run()
