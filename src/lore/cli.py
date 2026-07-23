from __future__ import annotations

import argparse
import sys


def _cmd_mcp_server(args: argparse.Namespace) -> None:
    from lore.mcp.server import create_server

    server = create_server()
    server.run(transport="stdio")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lore", description="Lore knowledge server")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("mcp-server", help="Start MCP server (stdio transport)")

    args = parser.parse_args(argv)

    if args.command == "mcp-server":
        _cmd_mcp_server(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
