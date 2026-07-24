from __future__ import annotations

import importlib.resources
import logging
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from lore.config.manager import get_global_config, get_project_config
from lore.git import GitError, get_git_interface, key_to_path
from lore.llm import LLMProvider
from lore.llm import get_llm_provider as _create_llm_provider
from lore.store import get_store as _create_store
from lore.store.base import KnowledgeEntry
from lore.store.priority import resolve_priority
from lore.store.sqlite import SQLiteStore

logger = logging.getLogger(__name__)


def _load_lore_instructions() -> str:
    lore_md = Path(".lore/LORE.md")
    if lore_md.exists():
        return lore_md.read_text()
    return importlib.resources.read_text("lore.mcp.skills", "LORE.md")


_store_instance: SQLiteStore | None = None
_llm_instance: LLMProvider | None = None


def _get_store() -> SQLiteStore:
    global _store_instance
    if _store_instance is not None:
        return _store_instance
    _store_instance = _create_store()
    return _store_instance


def _get_llm_provider() -> LLMProvider:
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance
    _llm_instance = _create_llm_provider()
    return _llm_instance


def _entry_to_dict(entry: KnowledgeEntry) -> dict:
    d = entry.__dict__.copy()
    d.pop("embedding", None)
    return d


_KEY_RE = re.compile(r"^[a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+$")
_SHARED_DELETE_ERR = "shared entry — submit PR to the knowledge repo to delete"


def _validate_key(key: str) -> None:
    if not _KEY_RE.match(key):
        raise ValueError(
            f"Invalid key format: '{key}'. "
            "Expected 'type:domain:slug' with alphanumeric, hyphens, underscores."
        )


def _create_shared_pr(
    key: str,
    content: str,
    frontmatter: dict,
    title: str,
    body: str,
    repo_url: str,
    repo_branch: str | None,
) -> str | None:
    try:
        cfg = get_global_config()
        git_iface = get_git_interface(cfg.git.provider)
        file_path = key_to_path(key)
        return git_iface.create_pr(
            repo_url=repo_url,
            file_path=file_path,
            content=content,
            frontmatter=frontmatter,
            title=title,
            body=body,
            branch=repo_branch or "main",
        )
    except GitError:
        logger.warning("PR creation failed for %s", key, exc_info=True)
        return None


def _resolve_level(level_name: str) -> tuple[int, str, str | None, str | None]:
    if level_name == "individual":
        return 0, "individual", None, None
    cfg = get_project_config()
    for h in cfg.hierarchy:
        if h.name == level_name:
            return h.level, level_name, h.repo, h.branch
    available = ["individual"] + [h.name for h in cfg.hierarchy if h.name]
    raise ValueError(f"Unknown level '{level_name}'. Available: {available}")


def create_server() -> FastMCP:
    server = FastMCP("lore", instructions=_load_lore_instructions())

    @server.tool()
    def query_knowledge(
        topic: str,
        level: str | None = None,
    ) -> dict:
        """Search knowledge base using full-text search.

        Args:
            topic: Search query for FTS5 matching against key, value, and tags.
            level: Optional level number to filter results (e.g. "0", "1", "2").

        Returns:
            FTS-ranked results with priority resolution. When the same key
            exists at multiple levels, the highest priority wins. Locked
            entries always win. Includes LLM synthesis when configured.
        """
        store = _get_store()

        filter_levels = None
        if level is not None:
            filter_levels = [int(level)]

        raw_results = store.query_fts(topic, limit=50, filter_levels=filter_levels)
        resolved = resolve_priority(raw_results)

        results = []
        for e in resolved:
            d = _entry_to_dict(e)
            d["priority"] = e.level
            results.append(d)

        synthesized = None
        cfg = get_global_config()
        if cfg.llm.provider != "none" and resolved:
            try:
                synthesized = _get_llm_provider().synthesize(topic, resolved)
            except Exception:
                logger.warning(
                    "LLM synthesis failed for topic %r", topic, exc_info=True
                )

        return {"results": results, "synthesized": synthesized}

    @server.tool()
    def list_knowledge(
        tag: str | None = None,
        level: str | None = None,
        include_history: bool = False,
    ) -> dict:
        """List knowledge entries with optional filters.

        Args:
            tag: Filter entries containing this tag.
            level: Filter to a specific level number (e.g. "0", "1").
            include_history: Include change history for each entry.

        Returns:
            List of knowledge entries, optionally with history records.
        """
        store = _get_store()

        level_int = int(level) if level is not None else None
        entries = store.list_entries(tag=tag, level=level_int)

        result_entries = []
        for entry in entries:
            d = _entry_to_dict(entry)
            if include_history:
                history = store.get_history(entry.id)
                d["history"] = [h.__dict__.copy() for h in history]
            result_entries.append(d)

        return {"entries": result_entries}

    @server.tool()
    def list_conflicts() -> dict:
        """List all knowledge entries that have conflicts.

        Returns both sides of each conflict linked together.
        """
        store = _get_store()

        conflict_entries = store.list_conflicts()

        conflicts = []
        for entry in conflict_entries:
            conflict_data = _entry_to_dict(entry)
            conflicting_entry = None
            if entry.conflict_with:
                other = store.get_by_id(entry.conflict_with)
                if other:
                    conflicting_entry = _entry_to_dict(other)

            conflicts.append(
                {
                    "entry": conflict_data,
                    "conflicting_entry": conflicting_entry,
                    "shared_key_pattern": entry.key,
                }
            )

        return {"conflicts": conflicts}

    @server.tool()
    def health_check() -> dict:
        """Check knowledge base health.

        Returns entry counts per level, conflict count, staleness info,
        and sync status.
        """
        store = _get_store()
        health = store.health()

        return {
            "total": health["total_entries"],
            "per_level": health["entries_by_level"],
            "conflicts": health["conflict_count"],
            "stale_count": health["stale_count"],
            "last_sync": {},
        }

    @server.tool()
    def store_knowledge(
        key: str,
        value: str,
        tags: str | None = None,
        level: str = "individual",
    ) -> dict:
        """Store a knowledge entry.

        Args:
            key: Knowledge key in 'type:domain:slug' format.
            value: The knowledge content to store.
            tags: Comma-separated tags for categorization.
            level: Target level — 'individual' for local-only, or a
                configured hierarchy level name for shared storage.

        Returns:
            Entry id, key, level, and pr_url (null for individual,
            PR URL for shared levels via GitInterface).
        """
        _validate_key(key)
        level_int, level_name, repo_url, repo_branch = _resolve_level(level)
        store = _get_store()

        existing = store.get_by_key_and_level(key, level_int)
        if existing:
            store.update(
                key,
                value,
                reason="updated via store_knowledge",
                actor="mcp",
                tags=tags,
                level=level_int,
            )
            entry_id = existing.id
        else:
            entry = KnowledgeEntry(
                key=key,
                value=value,
                tags=tags or "",
                level=level_int,
                level_name=level_name,
                repo_url=repo_url,
                repo_branch=repo_branch,
            )
            entry_id = store.store(entry)

        pr_url = None
        if level_int > 0 and repo_url:
            verb = "update" if existing else "add"
            tags_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
            fm = {"tags": tags_list, "created_by": "lore-agent"}
            pr_url = _create_shared_pr(
                key=key,
                content=value,
                frontmatter=fm,
                title=f"lore: {verb} {key}",
                body=f"Auto-generated by lore store_knowledge"
                f" at level '{level_name}'",
                repo_url=repo_url,
                repo_branch=repo_branch,
            )

        return {"id": entry_id, "key": key, "level": level_int, "pr_url": pr_url}

    @server.tool()
    def negate_knowledge(
        key: str,
        reason: str,
        level: str = "individual",
    ) -> dict:
        """Negate a knowledge entry, preserving why it was invalidated.

        Preferred over delete — agents see *why* something changed.

        Args:
            key: The knowledge key to negate.
            reason: Why this knowledge is being negated.
            level: Target level — 'individual' or a configured hierarchy
                level name.

        Returns:
            The negated key and pr_url (null for individual,
            PR URL for shared levels).
        """
        _validate_key(key)
        level_int, level_name, repo_url, repo_branch = _resolve_level(level)
        store = _get_store()
        existing = store.get_by_key_and_level(key, level_int)
        if existing is None:
            return {"error": f"Key not found: '{key}' at level '{level}'"}

        negation_value = f"[NEGATED] {reason}\n\nPrevious value: {existing.value}"
        store.update(key, negation_value, reason=reason, actor="mcp", level=level_int)

        pr_url = None
        if level_int > 0 and repo_url:
            fm = {"created_by": "lore-agent", "negated": True}
            pr_url = _create_shared_pr(
                key=key,
                content=negation_value,
                frontmatter=fm,
                title=f"lore: negate {key}",
                body=f"Auto-generated by lore negate_knowledge: {reason}",
                repo_url=repo_url,
                repo_branch=repo_branch,
            )

        return {"key": key, "negated": True, "pr_url": pr_url}

    @server.tool()
    def delete_knowledge(
        key: str,
        level: str = "individual",
    ) -> dict:
        """Delete a knowledge entry from the local store.

        Individual entries are deleted immediately. Shared entries must be
        deleted via a PR to the knowledge repo.

        Args:
            key: The knowledge key to delete.
            level: Target level — 'individual' or a configured hierarchy
                level name.

        Returns:
            Confirmation of deletion, or error for shared entries.
        """
        level_int, _, _, _ = _resolve_level(level)
        store = _get_store()
        existing = store.get_by_key_and_level(key, level_int)
        if existing is None:
            other = store.get(key)
            if other is not None and other.level > 0:
                return {"error": _SHARED_DELETE_ERR}
            return {"error": f"Key not found: '{key}' at level '{level}'"}

        if existing.level > 0:
            return {"error": _SHARED_DELETE_ERR}

        store.delete(key, reason="deleted via MCP", actor="mcp", level=level_int)
        return {"key": key, "deleted": True}

    return server
