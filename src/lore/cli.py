from __future__ import annotations

import argparse
import sys


def _cmd_mcp_server(args: argparse.Namespace) -> None:
    from lore.mcp.server import create_server

    server = create_server()
    server.run(transport="stdio")


def _cmd_sync(args: argparse.Namespace) -> None:
    from lore.config.manager import get_global_config
    from lore.config.utils import cache_dir, db_path, state_dir
    from lore.store.sqlite import SQLiteStore, create_schema
    from lore.sync.engine import SyncEngine
    from lore.sync.git import GitRepoManager
    from lore.sync.log import SyncLogWriter
    from lore.sync.state import SyncStateManager

    config = get_global_config()
    conn = create_schema(str(db_path()))
    store = SQLiteStore(conn)
    git_mgr = GitRepoManager(cache_dir() / "repos")
    state_mgr = SyncStateManager(state_dir() / "sync-state.json")
    log_writer = SyncLogWriter(state_dir() / "sync.md")

    engine = SyncEngine(store, git_mgr, state_mgr, log_writer)
    result = engine.sync_all(config.projects)

    print(
        f"Sync complete: {result.created} created, {result.updated} updated, "
        f"{result.deleted} deleted, {result.promoted} promoted"
    )
    if result.errors:
        for err in result.errors:
            print(f"  ERROR: {err}", file=sys.stderr)
    if args.verbose and result.details:
        for detail in result.details:
            print(f"  {detail}")

    sys.exit(1 if result.errors else 0)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lore", description="Lore knowledge server")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("mcp-server", help="Start MCP server (stdio transport)")

    sync_parser = sub.add_parser("sync", help="Sync knowledge repos")
    sync_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show per-file details"
    )

    args = parser.parse_args(argv)

    if args.command == "mcp-server":
        _cmd_mcp_server(args)
    elif args.command == "sync":
        _cmd_sync(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
