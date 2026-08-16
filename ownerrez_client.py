"""Backward-compatible re-export.

The client moved to ``ownerrez_mcp.client``. Import from there going forward.
"""

from ownerrez_mcp.client import OwnerRezClient, OwnerRezError, ReadOnlyError

__all__ = ["OwnerRezClient", "OwnerRezError", "ReadOnlyError"]
