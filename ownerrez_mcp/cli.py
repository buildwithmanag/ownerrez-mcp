"""Command-line entry point: `ownerrez-mcp [serve|auth|probe] [options]`.

`serve` is the default when no subcommand is given (how MCP clients launch it).
Each subcommand owns its own options, so `ownerrez-mcp probe --help` shows the
probe flags.
"""

from __future__ import annotations

import sys
from typing import List, Optional

from . import __version__

_HELP = """\
ownerrez-mcp — Model Context Protocol server for OwnerRez

usage: ownerrez-mcp [command] [options]

commands:
  serve     Run the MCP server over stdio (default if omitted).
  auth      Run the OAuth authorization flow and print an access token.
  probe     Probe the live API to confirm available endpoints.
            (see: ownerrez-mcp probe --help)
  webhook   Run the inbound-message webhook receiver (needs the [webhook] extra).

options:
  --version   Show version and exit.
  -h, --help  Show this help and exit.
"""


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] in {"-h", "--help"}:
        print(_HELP)
        return 0
    if argv and argv[0] == "--version":
        print(f"ownerrez-mcp {__version__}")
        return 0

    command = "serve"
    rest: List[str] = argv
    if argv and argv[0] in {"serve", "auth", "probe", "webhook"}:
        command, rest = argv[0], argv[1:]

    if command == "serve":
        from .server import run

        run()
        return 0
    if command == "auth":
        from .auth import run_oauth_flow

        return run_oauth_flow()
    if command == "probe":
        from .probe import main as probe_main

        return probe_main(rest)
    if command == "webhook":
        from .webhook import run as run_webhook

        return run_webhook()

    print(_HELP)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
