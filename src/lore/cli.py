from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def _ensure_dirs() -> None:
    from lore.config.utils import cache_dir, config_dir, data_dir, state_dir

    for d in (config_dir(), data_dir(), cache_dir(), state_dir()):
        d.mkdir(parents=True, exist_ok=True)


def _ensure_global_config() -> dict:
    from lore.config.utils import config_path

    path = config_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    default = {"lore": {"projects": []}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(default, indent=2) + "\n", encoding="utf-8")
    return default


def _load_existing_hierarchies(
    global_cfg: dict,
) -> list[tuple[str, list[dict]]]:
    from lore.config.loaders import load_project_config

    results = []
    for project_path in global_cfg.get("lore", {}).get("projects", []):
        p = Path(project_path)
        if not p.exists():
            continue
        raw = load_project_config(p)
        hierarchy = raw.get("lore", {}).get("hierarchy", [])
        if hierarchy:
            results.append((project_path, hierarchy))
    return results


def _prompt_hierarchy_interactive() -> list[dict]:
    try:
        count_str = input("How many shared levels? [0]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return []

    count = int(count_str) if count_str else 0
    if count <= 0:
        return []

    hierarchy = []
    for i in range(1, count + 1):
        print(f"\n--- Level {i} ---")
        try:
            repo = input("  Repo URL: ").strip()
            if not repo:
                print("  Skipping (no URL)")
                continue
            branch = input("  Branch [main]: ").strip() or "main"
            name = input("  Name (optional): ").strip() or None
        except (EOFError, KeyboardInterrupt):
            print()
            break

        entry: dict = {"level": i, "repo": repo, "branch": branch}
        if name:
            entry["name"] = name
        hierarchy.append(entry)

    return hierarchy


def _prompt_hierarchy(global_cfg: dict) -> list[dict]:
    existing = _load_existing_hierarchies(global_cfg)

    if not existing:
        return _prompt_hierarchy_interactive()

    print("\nExisting hierarchies:")
    for idx, (path, levels) in enumerate(existing, 1):
        names = [lv.get("name") or f"level-{lv['level']}" for lv in levels]
        print(f"  {idx}) {path} ({len(levels)} levels: {', '.join(names)})")
    print(f"  {len(existing) + 1}) Create new hierarchy")

    try:
        choice_str = input(f"Choose [1-{len(existing) + 1}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return []

    if not choice_str:
        return []

    choice = int(choice_str)
    if 1 <= choice <= len(existing):
        _, hierarchy = existing[choice - 1]
        print(f"  Reusing hierarchy from {existing[choice - 1][0]}")
        return hierarchy

    return _prompt_hierarchy_interactive()


def _write_project_config(hierarchy: list[dict]) -> None:
    lore_dir = Path.cwd() / ".lore"
    lore_dir.mkdir(exist_ok=True)
    config_file = lore_dir / "config.json"

    if config_file.exists():
        data = json.loads(config_file.read_text(encoding="utf-8"))
    else:
        data = {}

    data.setdefault("lore", {})
    data["lore"]["hierarchy"] = hierarchy
    config_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _register_project(global_cfg: dict) -> dict:
    from lore.config.utils import config_path

    cwd = str(Path.cwd())
    projects = global_cfg.setdefault("lore", {}).setdefault("projects", [])
    if cwd not in projects:
        projects.append(cwd)
        config_path().write_text(
            json.dumps(global_cfg, indent=2) + "\n", encoding="utf-8"
        )
    return global_cfg


def _register_mcp() -> None:
    claude_json = Path.home() / ".claude.json"

    if claude_json.exists():
        data = json.loads(claude_json.read_text(encoding="utf-8"))
    else:
        data = {}

    servers = data.setdefault("mcpServers", {})
    if "lore" in servers:
        return

    binary = shutil.which("lore")
    if not binary:
        print("  WARNING: 'lore' not found on PATH, using 'lore' as command")
        binary = "lore"

    servers["lore"] = {"command": binary, "args": ["mcp-server"]}
    claude_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _get_store():
    from lore.config.manager import get_global_config
    from lore.config.utils import db_path
    from lore.store.sqlite import SQLiteStore, create_schema

    cfg = get_global_config()
    path = cfg.store.path or str(db_path())
    conn = create_schema(path)
    return SQLiteStore(conn)


def _cmd_init(args: argparse.Namespace) -> int:
    from lore.config.utils import db_path
    from lore.store.sqlite import create_schema

    print("Initializing lore...")

    _ensure_dirs()
    print("  Created XDG directories")

    global_cfg = _ensure_global_config()
    print("  Global config ready")

    hierarchy = _prompt_hierarchy(global_cfg)
    _write_project_config(hierarchy)
    print(f"  Project config written ({len(hierarchy)} hierarchy levels)")

    db = db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    create_schema(str(db))
    print("  Database ready")

    global_cfg = _register_project(global_cfg)
    print("  Project registered")

    _register_mcp()
    print("  MCP server registered")

    if hierarchy:
        print("\nRunning first sync...")
        _cmd_sync(argparse.Namespace(verbose=False))
    else:
        print("\n  No hierarchy levels — skipping sync (solo mode)")

    print("\nDone.")
    return 0


def _cmd_mcp_server(args: argparse.Namespace) -> int:
    from lore.mcp.server import create_server

    server = create_server()
    server.run(transport="stdio")
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    from lore.config.manager import get_global_config
    from lore.config.utils import cache_dir, state_dir
    from lore.sync.engine import SyncEngine
    from lore.sync.git import GitRepoManager
    from lore.sync.log import SyncLogWriter
    from lore.sync.state import SyncStateManager

    store = _get_store()
    config = get_global_config()
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

    return 1 if result.errors else 0


def _cmd_search(args: argparse.Namespace) -> int:
    from lore.config.manager import get_project_config
    from lore.store.priority import resolve_priority

    store = _get_store()

    try:
        project_cfg = get_project_config()
    except Exception:
        print("Not in a lore project. Run 'lore init' first.", file=sys.stderr)
        return 1

    filter_levels = (
        [h.level for h in project_cfg.hierarchy] if project_cfg.hierarchy else None
    )
    filter_repos = (
        [(h.repo, h.branch) for h in project_cfg.hierarchy]
        if project_cfg.hierarchy
        else None
    )

    raw = store.query_fts(
        args.topic, limit=50, filter_levels=filter_levels, filter_repos=filter_repos
    )
    resolved = resolve_priority(raw)

    if not resolved:
        print("No results found.")
        return 0

    for entry in resolved:
        snippet = entry.value[:100]
        if len(entry.value) > 100:
            snippet += "..."
        locked = " [LOCKED]" if entry.locked else ""
        level_label = entry.level_name or f"L{entry.level}"
        print(f"  {entry.key}  ({level_label}){locked}")
        print(f"    {snippet}")
        print()

    print(f"{len(resolved)} result(s)")
    return 0


def _cmd_conflicts(args: argparse.Namespace) -> int:
    store = _get_store()
    conflicts = store.list_conflicts()

    if not conflicts:
        print("No conflicts.")
        return 0

    for entry in conflicts:
        snippet = entry.value[:80]
        if len(entry.value) > 80:
            snippet += "..."
        level_label = entry.level_name or f"L{entry.level}"
        status = entry.conflict_status or "unresolved"
        print(f"  {entry.key}  ({level_label})  status={status}")
        print(f"    {snippet}")
        if entry.conflict_with:
            print(f"    conflicts with: {entry.conflict_with}")
        print()

    print(f"{len(conflicts)} conflict(s)")
    return 0


# =====================================================================
# lore config
# =====================================================================


def _project_config_path() -> Path:
    return Path.cwd() / ".lore" / "config.json"


def _is_lore_project() -> bool:
    return (Path.cwd() / ".lore").is_dir()


def _load_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _set_nested(data: dict, keys: list[str], value) -> None:
    for key in keys[:-1]:
        data = data.setdefault(key, {})
    data[keys[-1]] = value


def _parse_value(raw: str):
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    if raw.lower() == "null":
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    if raw.startswith(("[", "{")):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return raw


def _cmd_config(args: argparse.Namespace) -> int:
    sub = getattr(args, "config_command", None)
    if sub == "show":
        return _cmd_config_show(args)
    elif sub == "set":
        return _cmd_config_set(args)
    elif sub == "edit":
        return _cmd_config_edit(args)
    else:
        print("Usage: lore config {show|set|edit}", file=sys.stderr)
        return 1


def _cmd_config_show(args: argparse.Namespace) -> int:
    from lore.config.loaders import _deep_merge
    from lore.config.utils import config_path

    use_global = getattr(args, "global_", False)
    use_project = getattr(args, "project", False)

    if use_project and not _is_lore_project():
        print("Not in a lore project. Run 'lore init' first.", file=sys.stderr)
        return 1

    global_data = _load_json_file(config_path())
    project_data = _load_json_file(_project_config_path()) if _is_lore_project() else {}

    if use_global:
        data = global_data
    elif use_project:
        data = project_data
    else:
        data = _deep_merge(global_data, project_data)

    print(json.dumps(data, indent=2))
    return 0


def _cmd_config_set(args: argparse.Namespace) -> int:
    from lore.config.loaders import _clear_config_cache
    from lore.config.utils import config_path

    use_global = getattr(args, "global_", False)

    if use_global:
        path = config_path()
    else:
        if not _is_lore_project():
            print(
                "Not in a lore project. Run 'lore init' first, " "or use --global.",
                file=sys.stderr,
            )
            return 1
        path = _project_config_path()

    data = _load_json_file(path)
    keys = args.key.split(".")
    value = _parse_value(args.value)
    _set_nested(data, keys, value)
    _write_json_file(path, data)
    _clear_config_cache()
    print(f"Set {args.key} = {json.dumps(value)}")
    return 0


def _cmd_config_edit(args: argparse.Namespace) -> int:
    import os
    import subprocess

    from lore.config.loaders import _clear_config_cache
    from lore.config.utils import config_path

    use_global = getattr(args, "global_", False)

    if use_global:
        path = config_path()
    else:
        if not _is_lore_project():
            print(
                "Not in a lore project. Run 'lore init' first, " "or use --global.",
                file=sys.stderr,
            )
            return 1
        path = _project_config_path()

    if not path.exists():
        _write_json_file(path, {})

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    result = subprocess.run([editor, str(path)])
    if result.returncode != 0:
        print("Editor exited with error.", file=sys.stderr)
        return 1

    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON after edit: {exc}", file=sys.stderr)
        return 1

    _clear_config_cache()
    print(f"Config saved: {path}")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lore", description="Lore knowledge server")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize lore in current directory")
    sub.add_parser("mcp-server", help="Start MCP server (stdio transport)")

    sync_parser = sub.add_parser("sync", help="Sync knowledge repos")
    sync_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show per-file details"
    )

    search_parser = sub.add_parser("search", help="Search knowledge base")
    search_parser.add_argument("topic", help="Search query")

    sub.add_parser("conflicts", help="Show conflict report")

    config_parser = sub.add_parser("config", help="View and edit configuration")
    config_sub = config_parser.add_subparsers(dest="config_command")

    show_parser = config_sub.add_parser("show", help="Display configuration")
    show_parser.add_argument(
        "--global", dest="global_", action="store_true", help="Show global config only"
    )
    show_parser.add_argument(
        "--project", action="store_true", help="Show project config only"
    )

    set_parser = config_sub.add_parser("set", help="Set a config value")
    set_parser.add_argument("key", help="Dot-notation key (e.g. lore.store.path)")
    set_parser.add_argument("value", help="Value to set")
    set_parser.add_argument(
        "--global", dest="global_", action="store_true", help="Set in global config"
    )

    edit_parser = config_sub.add_parser("edit", help="Open config in editor")
    edit_parser.add_argument(
        "--global", dest="global_", action="store_true", help="Edit global config"
    )

    args = parser.parse_args(argv)

    handlers = {
        "init": _cmd_init,
        "mcp-server": _cmd_mcp_server,
        "sync": _cmd_sync,
        "search": _cmd_search,
        "conflicts": _cmd_conflicts,
        "config": _cmd_config,
    }

    handler = handlers.get(args.command)
    if handler:
        sys.exit(handler(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
