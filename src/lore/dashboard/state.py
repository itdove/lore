from __future__ import annotations

import json
import logging

from lore.store.base import KnowledgeEntry, validate_key  # noqa: F401
from lore.store.sqlite import SQLiteStore

logger = logging.getLogger(__name__)

_store_instance: SQLiteStore | None = None


def get_dashboard_store() -> SQLiteStore:
    global _store_instance
    if _store_instance is not None:
        return _store_instance
    from lore.store import get_store

    _store_instance = get_store()
    return _store_instance


def reset_store() -> None:
    global _store_instance
    _store_instance = None


def get_sync_status() -> dict:
    from lore.sync.helpers import get_sync_status_dict

    return get_sync_status_dict()


def trigger_sync():
    from lore.sync.helpers import run_sync

    return run_sync(get_dashboard_store())


def build_repo_file_url(entry: KnowledgeEntry) -> str | None:
    if not entry.repo_url or not entry.provenance:
        return None

    try:
        prov = json.loads(entry.provenance)
    except (json.JSONDecodeError, TypeError):
        return None

    file_path = prov.get("file_path")
    if not file_path:
        return None

    url = entry.repo_url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    if not url.startswith(("https://", "http://")):
        return None

    branch = entry.repo_branch or "main"

    if "github.com" in url:
        return f"{url}/blob/{branch}/{file_path}"
    if "gitlab.com" in url:
        return f"{url}/-/blob/{branch}/{file_path}"

    return f"{url}/blob/{branch}/{file_path}"


def promote_entry(entry: KnowledgeEntry) -> dict:
    from lore.config.manager import get_global_config, get_project_config
    from lore.git import GitError, get_git_interface, key_to_path

    if entry.level != 0:
        return {"error": "Only individual (level 0) entries can be promoted"}

    fresh = get_dashboard_store().get_by_key_and_level(entry.key, 0)
    if not fresh:
        return {"error": "Entry no longer exists"}
    entry = fresh

    try:
        project_cfg = get_project_config()
    except Exception:
        return {"error": "Not in a lore project with hierarchy configured"}

    if not project_cfg.hierarchy:
        return {"error": "No hierarchy levels configured — nowhere to promote to"}

    target = project_cfg.hierarchy[0]

    try:
        cfg = get_global_config()
        git_iface = get_git_interface(cfg.git.provider)
        file_path = key_to_path(entry.key)

        tags_list = [t.strip() for t in (entry.tags or "").split(",") if t.strip()]
        fm = {"tags": tags_list, "created_by": "lore-dashboard"}

        pr_url = git_iface.create_pr(
            repo_url=target.repo,
            file_path=file_path,
            content=entry.value,
            frontmatter=fm,
            title=f"lore: promote {entry.key}",
            body=f"Promoted from individual to {target.name or f'level-{target.level}'}"
            f" via lore dashboard",
            branch=target.branch,
        )
        return {"pr_url": pr_url}
    except GitError as exc:
        logger.warning("Promote PR failed for %s", entry.key, exc_info=True)
        return {"error": str(exc)}
