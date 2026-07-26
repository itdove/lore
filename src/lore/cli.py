from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

_RECALL_PREAMBLE = "IMPORTANT: The following team knowledge is relevant to this prompt."


def _ensure_dirs() -> None:
    from lore.config.utils import cache_dir, config_dir, data_dir, state_dir

    for d in (config_dir(), data_dir(), cache_dir(), state_dir()):
        d.mkdir(parents=True, exist_ok=True)


def _ensure_global_config() -> dict:
    from lore.config.utils import config_path

    path = config_path()
    data = _load_json_file(path)
    if data:
        return data
    default = {"lore": {"projects": []}}
    _write_json_file(path, default)
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

    try:
        count = int(count_str) if count_str else 0
    except ValueError:
        print("  Invalid number, using 0.")
        count = 0
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
            description = input("  Description (optional): ").strip() or None
            writable_str = input("  Writable by agents? [Y/n]: ").strip().lower()
            writable = writable_str not in ("n", "no")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        entry: dict = {"level": i, "repo": repo, "branch": branch}
        if name:
            entry["name"] = name
        if description:
            entry["description"] = description
        if not writable:
            entry["writable"] = False
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

    try:
        choice = int(choice_str)
    except ValueError:
        return _prompt_hierarchy_interactive()
    if 1 <= choice <= len(existing):
        _, hierarchy = existing[choice - 1]
        print(f"  Reusing hierarchy from {existing[choice - 1][0]}")
        return hierarchy

    return _prompt_hierarchy_interactive()


def _prompt_global_providers(global_cfg: dict) -> dict:
    from lore.config.loaders import save_config
    from lore.config.utils import config_path

    lore = global_cfg.setdefault("lore", {})
    search = lore.setdefault("search", {})

    if search.get("embedding_provider"):
        print("  Global embedding already configured, skipping prompt")
        return global_cfg

    print("\nGlobal embedding settings (shared across all projects):")

    try:
        emb = input("  Embedding provider [none/ollama] (ollama): ").strip().lower()
        search["embedding_provider"] = "none" if emb == "none" else "ollama"
        if search["embedding_provider"] == "ollama":
            model = input("  Embedding model (nomic-embed-text): ").strip()
            search["embedding_model"] = model or "nomic-embed-text"
    except (EOFError, KeyboardInterrupt):
        print()

    save_config(config_path(), global_cfg)
    return global_cfg


def _write_project_config(hierarchy: list[dict]) -> None:
    path = _project_config_path()
    path.parent.mkdir(exist_ok=True)
    data = _load_json_file(path)
    data.setdefault("lore", {})
    data["lore"]["hierarchy"] = hierarchy
    _write_json_file(path, data)


def _register_project(global_cfg: dict) -> dict:
    from lore.config.utils import config_path

    cwd = str(Path.cwd())
    projects = global_cfg.setdefault("lore", {}).setdefault("projects", [])
    if cwd not in projects:
        projects.append(cwd)
        _write_json_file(config_path(), global_cfg)
    return global_cfg


def _register_mcp() -> None:
    mcp_json = Path.cwd() / ".mcp.json"
    data = _load_json_file(mcp_json)

    servers = data.setdefault("mcpServers", {})
    if "lore" in servers:
        return

    binary = shutil.which("lore")
    if not binary:
        print("  WARNING: 'lore' not found on PATH, using 'lore' as command")
        binary = "lore"

    servers["lore"] = {"command": binary, "args": ["mcp-server"]}
    _write_json_file(mcp_json, data)


def _has_hook_command(matchers: list[dict], command: str) -> bool:
    return any(
        h.get("command") == command for m in matchers for h in m.get("hooks", [])
    )


def _register_hooks() -> None:
    settings_path = Path.cwd() / ".claude" / "settings.json"
    data = _load_json_file(settings_path)
    hooks = data.setdefault("hooks", {})

    changed = False

    desired = {
        "UserPromptSubmit": "lore hook recall",
        "PostToolUse": "lore hook nudge",
        "SessionEnd": "lore hook capture",
    }

    for event, command in desired.items():
        matchers = hooks.get(event, [])
        if _has_hook_command(matchers, command):
            continue
        matchers.append(
            {"matcher": "", "hooks": [{"type": "command", "command": command}]}
        )
        hooks[event] = matchers
        changed = True

    if changed:
        _write_json_file(settings_path, data)


def _enable_mcp_server_trust() -> None:
    settings_path = Path.home() / ".claude" / "settings.json"
    data = _load_json_file(settings_path)
    servers = data.setdefault("enabledMcpjsonServers", [])
    if "lore" not in servers:
        servers.append("lore")
        _write_json_file(settings_path, data)


def _allow_mcp_tools() -> None:
    settings_path = Path.cwd() / ".claude" / "settings.json"
    data = _load_json_file(settings_path)
    permissions = data.setdefault("permissions", {})
    allowed = permissions.setdefault("allow", [])
    tool_pattern = "mcp__lore__*"
    if tool_pattern not in allowed:
        allowed.append(tool_pattern)
        _write_json_file(settings_path, data)


def _get_store():
    from lore.store import get_store

    return get_store()


def _cmd_init(args: argparse.Namespace) -> int:
    from lore.config.utils import db_path
    from lore.store import sqlite as sqlite_mod
    from lore.store.sqlite import create_schema

    print("Initializing lore...")

    _ensure_dirs()
    print("  Created XDG directories")

    global_cfg = _ensure_global_config()
    print("  Global config ready")

    if getattr(args, "no_levels", False):
        hierarchy = []
    else:
        hierarchy = _prompt_hierarchy(global_cfg)
    _write_project_config(hierarchy)
    print(f"  Project config written ({len(hierarchy)} hierarchy levels)")

    global_cfg = _prompt_global_providers(global_cfg)
    print("  Global providers configured")

    db = db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    create_schema(str(db))
    print("  Database ready")
    if not sqlite_mod._VEC_LOADED:
        print(
            "  WARNING: sqlite-vec extension not loaded — "
            "vector search will use slower Python fallback.\n"
            "  See README.md 'Vector Search Performance' for rebuild instructions."
        )

    global_cfg = _register_project(global_cfg)
    print("  Project registered")

    _register_mcp()
    print("  MCP server registered (.mcp.json)")

    _register_hooks()
    print("  Hooks registered (.claude/settings.json)")

    _allow_mcp_tools()
    print("  MCP tool permissions added (.claude/settings.json)")

    _enable_mcp_server_trust()
    print("  MCP server trusted (~/.claude/settings.json)")

    if hierarchy:
        print("\nRunning first sync...")
        _cmd_sync(argparse.Namespace(verbose=False, status=False, force=True))
    else:
        print("\n  No hierarchy levels — skipping sync (solo mode)")

    print("\nDone.")
    return 0


def _cmd_mcp_server(args: argparse.Namespace) -> int:
    from lore.mcp.server import create_server

    server = create_server()
    server.run(transport="stdio")
    return 0


def _cmd_sync_status(args: argparse.Namespace) -> int:
    from lore.sync.helpers import get_sync_status_dict

    status = get_sync_status_dict()
    print(f"Last sync: {status['last_sync'] or 'never'}")
    print(f"Staleness threshold: {status['threshold_minutes']} minutes")
    print(f"Status: {'STALE' if status['stale'] else 'FRESH'}")
    print(f"Auto-sync: {'enabled' if status['auto_sync'] else 'disabled'}")
    print(f"Sync in progress: {'yes' if status['locked'] else 'no'}")
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    if getattr(args, "status", False):
        return _cmd_sync_status(args)

    from lore.sync.helpers import get_sync_status_dict, run_sync

    if not getattr(args, "force", False):
        status = get_sync_status_dict()
        if not status["stale"]:
            print("Knowledge base is fresh. Use --force to sync anyway.")
            return 0

    try:
        result = run_sync(_get_store(), force=getattr(args, "force", False))

        print(
            f"Sync complete: {result.created} created, {result.updated} updated, "
            f"{result.deleted} deleted, {result.promoted} promoted"
        )
        if result.errors:
            for err in result.errors:
                print(f"  ERROR: {err}", file=sys.stderr)
        if getattr(args, "verbose", False) and result.details:
            for detail in result.details:
                print(f"  {detail}")

        from lore.store import sqlite as sqlite_mod

        if not sqlite_mod._VEC_LOADED:
            print(
                "WARNING: sqlite-vec not loaded — vector search using Python fallback."
            )

        return 1 if result.errors else 0
    except RuntimeError:
        print("Sync already in progress (lock held).", file=sys.stderr)
        return 1


def _cmd_search(args: argparse.Namespace) -> int:
    import logging

    from lore.config.manager import get_global_config, get_project_config
    from lore.store.priority import resolve_priority

    logger = logging.getLogger(__name__)
    store = _get_store()

    try:
        project_cfg = get_project_config()
    except Exception:
        print("Not in a lore project. Run 'lore init' first.", file=sys.stderr)
        return 1

    filter_levels, filter_repos = _build_hierarchy_filters(project_cfg.hierarchy)

    query_embedding = None
    cfg = get_global_config()
    if cfg.search.embedding_provider != "none":
        try:
            from lore.embedding import get_embedding_provider

            query_embedding = get_embedding_provider().embed(args.topic)
        except Exception:
            logger.warning(
                "Embedding failed for query %r, falling back to FTS",
                args.topic,
                exc_info=True,
            )

    raw = store.query_hybrid(
        args.topic,
        query_embedding=query_embedding,
        limit=50,
        filter_levels=filter_levels,
        filter_repos=filter_repos,
        min_similarity=cfg.search.min_similarity,
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
    from lore.config.utils import is_project

    return is_project()


def _resolve_config_path(use_global: bool) -> Path | None:
    from lore.config.utils import config_path

    if use_global:
        return config_path()
    if not _is_lore_project():
        print(
            "Not in a lore project. Run 'lore init' first, or use --global.",
            file=sys.stderr,
        )
        return None
    return _project_config_path()


def _build_hierarchy_filters(
    hierarchy: list,
) -> tuple[list[int] | None, list[tuple[str, str]] | None]:
    if not hierarchy:
        return None, None
    return (
        [h.level for h in hierarchy],
        [(h.repo, h.branch) for h in hierarchy],
    )


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
    elif sub == "add-level":
        return _cmd_config_add_level(args)
    else:
        print(
            "Usage: lore config {show|set|edit|add-level}",
            file=sys.stderr,
        )
        return 1


def _cmd_config_show(args: argparse.Namespace) -> int:
    from lore.config.loaders import deep_merge
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
        data = deep_merge(global_data, project_data)

    print(json.dumps(data, indent=2))
    return 0


def _cmd_config_set(args: argparse.Namespace) -> int:
    from lore.config.loaders import save_config
    from lore.config.manager import GLOBAL_ONLY_SUBKEYS
    from lore.config.utils import config_path

    stripped = args.key.removeprefix("lore.")
    if stripped in GLOBAL_ONLY_SUBKEYS:
        path = config_path()
        print(
            f"  (routing to global config — {stripped} "
            "must be consistent across projects)"
        )
    else:
        path = _resolve_config_path(getattr(args, "global_", False))
        if path is None:
            return 1

    data = _load_json_file(path)
    keys = args.key.split(".")
    value = _parse_value(args.value)
    _set_nested(data, keys, value)
    save_config(path, data)
    print(f"Set {args.key} = {json.dumps(value)}")
    return 0


def _cmd_config_edit(args: argparse.Namespace) -> int:
    import os
    import subprocess

    from lore.config.loaders import _clear_config_cache  # noqa: F811

    path = _resolve_config_path(getattr(args, "global_", False))
    if path is None:
        return 1

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


def _cmd_config_add_level(args: argparse.Namespace) -> int:
    from lore.config.loaders import save_config

    path = _project_config_path()
    if not path.parent.exists():
        print(
            "Not in a lore project. Run 'lore init --no-levels' first.",
            file=sys.stderr,
        )
        return 1

    data = _load_json_file(path)
    lore = data.setdefault("lore", {})
    hierarchy = lore.setdefault("hierarchy", [])

    for h in hierarchy:
        if h.get("level") == args.level:
            print(
                f"Level {args.level} already exists. "
                "Remove it first or use a different number.",
                file=sys.stderr,
            )
            return 1

    entry: dict = {
        "level": args.level,
        "repo": args.repo,
        "branch": args.branch,
        "name": args.name,
    }
    if args.description:
        entry["description"] = args.description
    if not args.writable:
        entry["writable"] = False

    hierarchy.append(entry)
    hierarchy.sort(key=lambda h: h.get("level", 0))
    save_config(path, data)

    rw = "writable" if args.writable else "read-only"
    print(f"Added level {args.level} ({args.name}, {rw})")
    print(f"  repo: {args.repo}@{args.branch}")
    if args.description:
        print(f"  description: {args.description}")
    print("\nRun 'lore sync --force' to pull knowledge from this level.")
    return 0


# =====================================================================
# lore hook
# =====================================================================


def _cmd_dashboard(args: argparse.Namespace) -> int:
    from lore.dashboard import launch

    if args.host != "127.0.0.1":
        print(
            f"WARNING: Binding to {args.host} exposes the dashboard "
            "without authentication. Use only on trusted networks.",
            file=sys.stderr,
        )

    try:
        launch(host=args.host, port=args.port)
    except KeyboardInterrupt:
        pass
    return 0


def _cmd_hook(args: argparse.Namespace) -> int:
    sub = getattr(args, "hook_command", None)
    if sub == "recall":
        return _cmd_hook_recall(args)
    elif sub == "nudge":
        return _cmd_hook_nudge(args)
    elif sub == "capture":
        return _cmd_hook_capture(args)
    else:
        print("Usage: lore hook {recall|nudge|capture}", file=sys.stderr)
        return 1


def _maybe_trigger_auto_sync() -> None:
    import subprocess

    from lore.config.manager import get_global_config
    from lore.config.utils import sync_lock_path, sync_state_path
    from lore.sync.lock import SyncLockManager
    from lore.sync.state import SyncStateManager, is_stale

    try:
        config = get_global_config()
        if not config.sync.auto_sync or not config.sync.on_session_start:
            return

        lock_mgr = SyncLockManager(sync_lock_path())
        if lock_mgr.is_locked:
            return

        state_mgr = SyncStateManager(sync_state_path())
        last_sync = state_mgr.last_sync_time()

        if not is_stale(last_sync, config.sync.staleness_threshold_minutes):
            return

        subprocess.Popen(
            ["lore", "sync"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        import logging

        logging.getLogger("lore").debug("auto-sync trigger failed", exc_info=True)


def _cmd_hook_recall(args: argparse.Namespace) -> int:
    payload = sys.stdin.read()
    if not payload.strip():
        return 0

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return 0

    prompt = data.get("user_message", "")
    if not prompt:
        return 0

    if not _is_lore_project():
        return 0

    _maybe_trigger_auto_sync()

    try:
        from lore.config.manager import get_project_config
        from lore.store.priority import resolve_priority

        store = _get_store()
        project_cfg = get_project_config()
        filter_levels, filter_repos = _build_hierarchy_filters(project_cfg.hierarchy)

        raw = store.query_fts(
            prompt, limit=10, filter_levels=filter_levels, filter_repos=filter_repos
        )
        resolved = resolve_priority(raw)

        if resolved:
            lines = [
                "<lore-context>",
                _RECALL_PREAMBLE,
            ]
            for entry in resolved:
                level_label = entry.level_name or f"L{entry.level}"
                lines.append(f"[{level_label}] {entry.key}: {entry.value}")
            lines.append("</lore-context>")
            print("\n".join(lines))
    except Exception as exc:
        print(f"lore hook recall error: {exc}", file=sys.stderr)

    return 0


def _cmd_hook_nudge(args: argparse.Namespace) -> int:
    return 0


def _cmd_hook_capture(args: argparse.Namespace) -> int:
    import sys

    from lore.capture import capture_knowledge
    from lore.config.manager import get_global_config, get_project_config
    from lore.git import GitError, get_git_interface, key_to_path
    from lore.llm import get_llm_provider
    from lore.store.base import KnowledgeEntry

    transcript = sys.stdin.read()
    if not transcript.strip():
        return 0

    try:
        cfg = get_global_config()
        if cfg.llm.provider == "none":
            return 0
        provider = get_llm_provider()
    except Exception as exc:
        print(f"Capture skipped: {exc}", file=sys.stderr)
        return 0

    store = _get_store()
    try:
        project_cfg = get_project_config()
    except Exception:
        project_cfg = None

    result = capture_knowledge(transcript, store, provider, project_cfg, cfg.capture)

    if not result.candidates:
        return 0

    writable_levels = {}
    if project_cfg:
        for h in project_cfg.hierarchy:
            if h.writable:
                writable_levels[h.name] = (h.level, h.repo, h.branch)

    stored = 0
    prs = 0
    negated = 0
    proposed = []
    out = sys.stderr

    for c in result.new:
        level_info = writable_levels.get(c.suggested_level)
        if level_info and level_info[1]:
            if cfg.capture.auto_pr_shared:
                try:
                    git_iface = get_git_interface(cfg.git.provider)
                    tags_list = c.tags if isinstance(c.tags, list) else []
                    fm = {"tags": tags_list, "created_by": "lore-capture"}
                    git_iface.create_pr(
                        repo_url=level_info[1],
                        file_path=key_to_path(c.key),
                        content=c.value,
                        frontmatter=fm,
                        title=f"lore: capture {c.key}",
                        body="Auto-captured from session transcript",
                        branch=level_info[2],
                    )
                    prs += 1
                except GitError:
                    pass
            else:
                proposed.append((c, c.suggested_level))
        elif cfg.capture.auto_store_individual:
            entry = KnowledgeEntry(
                key=c.key,
                value=c.value,
                tags=",".join(c.tags) if c.tags else "",
                level=0,
                level_name="individual",
            )
            store.store(entry)
            stored += 1
        else:
            proposed.append((c, "individual"))

    for action in result.enrichments:
        c = action.candidate
        try:
            store.update(
                action.existing_key,
                f"{action.existing_value}\n\n{c.value}",
                reason=f"enriched via capture (dist={action.distance:.4f})",
                actor="capture",
                level=0,
            )
            print(
                f"  [ENRICH] {action.existing_key} ← {c.key}",
                file=out,
            )
            stored += 1
        except (KeyError, ValueError):
            pass

    for c in result.updates:
        try:
            store.update(
                c.key,
                c.value,
                reason="updated via session capture",
                actor="capture",
                level=0,
            )
            stored += 1
        except (KeyError, ValueError):
            pass

    for c in result.negations:
        if c.negate_key:
            try:
                store.negate(
                    c.negate_key,
                    c.negate_reason or "contradicted by session",
                )
                negated += 1
            except (KeyError, ValueError):
                pass

    for action in result.skipped:
        c = action.candidate
        if action.action == "exact_match":
            print(f"  [SKIP] {c.key} — already exists", file=out)
        elif action.action == "rate_limited":
            print(f"  [SKIP] {c.key} — rate limited", file=out)

    print("\nKnowledge captured from session:", file=out)
    if stored:
        print(f"  {stored} stored", file=out)
    if prs:
        print(f"  {prs} PRs created", file=out)
    if negated:
        print(f"  {negated} negated", file=out)

    for c, level in proposed:
        snippet = c.value[:80].replace("\n", " ")
        print(f"  [PROPOSE] {c.key} → {level} level", file=out)
        print(f'    "{snippet}..."', file=out)
        print(
            f'    Run: lore store --key "{c.key}" --level {level}',
            file=out,
        )

    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lore", description="Lore knowledge server")
    sub = parser.add_subparsers(dest="command")

    init_parser = sub.add_parser("init", help="Initialize lore in current directory")
    init_parser.add_argument(
        "--no-levels",
        action="store_true",
        help="Skip hierarchy level prompts (add later with lore config add-level)",
    )
    sub.add_parser("mcp-server", help="Start MCP server (stdio transport)")

    sync_parser = sub.add_parser("sync", help="Sync knowledge repos")
    sync_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show per-file details"
    )
    sync_parser.add_argument(
        "--status", action="store_true", help="Show sync status and staleness"
    )
    sync_parser.add_argument(
        "--force", action="store_true", help="Force sync regardless of staleness"
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

    add_level_parser = config_sub.add_parser(
        "add-level", help="Add a hierarchy level to project config"
    )
    add_level_parser.add_argument(
        "--level", type=int, required=True, help="Level number (1, 2, ...)"
    )
    add_level_parser.add_argument(
        "--name", required=True, help="Level name (e.g. team, org)"
    )
    add_level_parser.add_argument("--repo", required=True, help="Git repo URL")
    add_level_parser.add_argument(
        "--branch", default="main", help="Git branch (default: main)"
    )
    add_level_parser.add_argument(
        "--writable",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Allow agents to write (default: true)",
    )
    add_level_parser.add_argument(
        "--description", default=None, help="Level description for LLM capture"
    )

    dashboard_parser = sub.add_parser("dashboard", help="Launch web dashboard")
    dashboard_parser.add_argument(
        "--port", type=int, default=8765, help="Port (default: 8765)"
    )
    dashboard_parser.add_argument(
        "--host", default="127.0.0.1", help="Host (default: 127.0.0.1)"
    )

    hook_parser = sub.add_parser("hook", help="Claude Code hook handlers")
    hook_sub = hook_parser.add_subparsers(dest="hook_command")
    hook_sub.add_parser("recall", help="Recall context (UserPromptSubmit)")
    hook_sub.add_parser("nudge", help="Mid-session nudge (PostToolUse)")
    hook_sub.add_parser("capture", help="Capture knowledge (SessionEnd)")

    args = parser.parse_args(argv)

    handlers = {
        "init": _cmd_init,
        "mcp-server": _cmd_mcp_server,
        "sync": _cmd_sync,
        "search": _cmd_search,
        "conflicts": _cmd_conflicts,
        "dashboard": _cmd_dashboard,
        "config": _cmd_config,
        "hook": _cmd_hook,
    }

    handler = handlers.get(args.command)
    if handler:
        sys.exit(handler(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
