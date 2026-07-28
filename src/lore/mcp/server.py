from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from lore.config.manager import get_global_config, get_project_config
from lore.config.models import (
    IMPLICIT_LEVELS,
    INDIVIDUAL_LEVEL,
    PROJECT_LEVEL,
    LevelPolicy,
)
from lore.config.utils import get_project_remote
from lore.embedding import EmbeddingProvider
from lore.embedding import get_embedding_provider as _create_embedding_provider
from lore.embedding.base import embed_to_blob
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
_embedding_instance: EmbeddingProvider | None = None


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


def _get_embedding_provider() -> EmbeddingProvider:
    global _embedding_instance
    if _embedding_instance is not None:
        return _embedding_instance
    _embedding_instance = _create_embedding_provider()
    return _embedding_instance


def _entry_to_dict(entry: KnowledgeEntry) -> dict:
    d = entry.__dict__.copy()
    d.pop("embedding", None)
    return d


_SHARED_DELETE_ERR = "shared entry — submit PR to the knowledge repo to delete"


def _validate_key(key: str) -> None:
    from lore.store.base import validate_key

    err = validate_key(key)
    if err:
        raise ValueError(f"Invalid key format: '{key}'. {err}")


def _create_shared_pr(
    key: str,
    content: str,
    frontmatter: dict,
    title: str,
    body: str,
    repo_url: str,
    repo_branch: str | None,
    file_path_override: str | None = None,
) -> str | None:
    try:
        cfg = get_global_config()
        git_iface = get_git_interface(cfg.git.provider)
        file_path = file_path_override or key_to_path(key)
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


def _submit_pr(
    policy: LevelPolicy,
    key: str,
    content: str,
    frontmatter: dict,
    title: str,
    body: str,
) -> str | None:
    if not (policy.creates_pr and policy.repo_url):
        return None
    override = (
        f"{policy.pr_path_prefix}{key_to_path(key)}" if policy.pr_path_prefix else None
    )
    return _create_shared_pr(
        key=key,
        content=content,
        frontmatter=frontmatter,
        title=title,
        body=body,
        repo_url=policy.repo_url,
        repo_branch=policy.repo_branch,
        file_path_override=override,
    )


def _resolve_level(level_name: str) -> LevelPolicy:
    if level_name == "individual":
        return LevelPolicy(
            level=INDIVIDUAL_LEVEL,
            name="individual",
            repo_url=None,
            repo_branch=None,
            writable=True,
            stores_locally=True,
            creates_pr=False,
            locally_deletable=True,
            pr_path_prefix=None,
        )
    if level_name == "project":
        repo_url, repo_branch = get_project_remote()
        return LevelPolicy(
            level=PROJECT_LEVEL,
            name="project",
            repo_url=repo_url,
            repo_branch=repo_branch,
            writable=True,
            stores_locally=False,
            creates_pr=True,
            locally_deletable=False,
            pr_path_prefix=".lore/knowledge/",
        )
    cfg = get_project_config()
    for h in cfg.hierarchy:
        if h.name == level_name:
            return LevelPolicy(
                level=h.level,
                name=level_name,
                repo_url=h.repo,
                repo_branch=h.branch,
                writable=h.writable,
                stores_locally=False,
                creates_pr=True,
                locally_deletable=False,
                pr_path_prefix=None,
            )
    available = ["individual", "project"] + [h.name for h in cfg.hierarchy if h.name]
    raise ValueError(f"Unknown level '{level_name}'. Available: {available}")


def _assert_writable(level_name: str, writable: bool) -> None:
    if not writable:
        raise ValueError(
            f"Level '{level_name}' is read-only. "
            "Knowledge at this level is maintained via "
            "git commits to the knowledge repo."
        )


def create_server() -> FastMCP:
    server = FastMCP("lore", instructions=_load_lore_instructions())

    @server.tool()
    def query_knowledge(
        topic: str,
        level: str | None = None,
        limit: int = 10,
    ) -> dict:
        """Search knowledge base using hybrid search (FTS + vector + RRF).

        Results are returned in relevance order (best match first).
        Use limit to control how many results you need — start with
        a small limit (3-5) for targeted lookups.

        Args:
            topic: Search query. Matched against key, value, and tags via
                FTS5, and semantically via vector embeddings when configured.
            level: Optional level number to filter results (e.g. "0", "1", "2").
            limit: Max results to return (default 10). Use 3-5 for
                targeted queries, higher for broad exploration.

        Returns:
            Hybrid-ranked results with priority resolution. When the same key
            exists at multiple levels, the highest priority wins. Locked
            entries always win. Includes LLM synthesis when configured.
        """
        store = _get_store()

        filter_levels = None
        if level is not None:
            filter_levels = [int(level)]

        query_embedding = None
        cfg = get_global_config()
        if cfg.search.embedding_provider != "none":
            try:
                query_embedding = _get_embedding_provider().embed(topic)
            except Exception:
                logger.warning(
                    "Embedding failed for topic %r, falling back to FTS",
                    topic,
                    exc_info=True,
                )

        raw_results = store.query_hybrid(
            topic,
            query_embedding=query_embedding,
            limit=limit,
            filter_levels=filter_levels,
            min_similarity=cfg.search.min_similarity,
        )
        resolved = resolve_priority(raw_results)

        results = []
        for e in resolved:
            d = _entry_to_dict(e)
            d["priority"] = e.level
            results.append(d)

        synthesized = None
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
            "negated_count": health.get("negated_count", 0),
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
            key: Knowledge key in colon-separated format (e.g., 'bug:api:jwt').
            value: The knowledge content to store.
            tags: Comma-separated tags for categorization.
            level: Target level — 'individual' for local-only, 'project'
                for project-scoped (SQLite + PR to .lore/knowledge/),
                or a configured hierarchy level name for shared storage.

        Returns:
            Entry id, key, level, and pr_url (null for individual,
            PR URL for project and shared levels via GitInterface).
        """
        _validate_key(key)
        policy = _resolve_level(level)
        _assert_writable(level, policy.writable)
        store = _get_store()
        cfg = get_global_config()

        embedding_blob = None
        if cfg.search.embedding_provider != "none":
            try:
                emb_vec = _get_embedding_provider().embed(f"{key} {value}")
                if emb_vec:
                    embedding_blob = embed_to_blob(emb_vec)
                    dupes = store.query_vector(
                        emb_vec, limit=1, filter_levels=[policy.level]
                    )
                    if dupes:
                        closest, dist = dupes[0]
                        if (
                            dist < cfg.search.dedup_threshold
                            and closest.level == policy.level
                        ):
                            store.update(
                                closest.key,
                                closest.value,
                                reason=f"reinforced (cosine dist={dist:.4f})",
                                actor="mcp",
                                level=closest.level,
                            )
                            return {
                                "id": closest.id,
                                "key": closest.key,
                                "level": closest.level,
                                "deduplicated": True,
                                "distance": round(dist, 4),
                                "pr_url": None,
                            }
            except Exception:
                logger.warning("Embedding failed for key %r", key, exc_info=True)

        tags_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        fm = {"tags": tags_list, "created_by": "lore-agent"}

        pr_url = _submit_pr(
            policy,
            key=key,
            content=value,
            frontmatter=fm,
            title=f"lore: add {key}",
            body=f"Auto-generated by lore store_knowledge" f" at level '{policy.name}'",
        )
        if pr_url is not None and not policy.stores_locally:
            return {
                "key": key,
                "level": policy.level,
                "pr_url": pr_url,
            }

        existing = store.get_by_key_and_level(key, policy.level)
        if existing:
            store.update(
                key,
                value,
                reason="updated via store_knowledge",
                actor="mcp",
                tags=tags,
                level=policy.level,
            )
            entry_id = existing.id
        else:
            entry = KnowledgeEntry(
                key=key,
                value=value,
                tags=tags or "",
                level=policy.level,
                level_name=policy.name,
                embedding=embedding_blob,
            )
            entry_id = store.store(entry)

        return {"id": entry_id, "key": key, "level": policy.level, "pr_url": pr_url}

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
            level: Target level — 'individual', 'project', or a configured
                hierarchy level name.

        Returns:
            The negated key and pr_url (null for individual,
            PR URL for project and shared levels).
        """
        _validate_key(key)
        policy = _resolve_level(level)
        _assert_writable(level, policy.writable)
        store = _get_store()
        existing = store.get_by_key_and_level(key, policy.level)
        if existing is None:
            return {"error": f"Key not found: '{key}' at level '{level}'"}

        negation_content = f"[NEGATED] {reason}\n\n" f"Previous value: {existing.value}"
        fm = {"created_by": "lore-agent", "negated": True}

        pr_url = _submit_pr(
            policy,
            key=key,
            content=negation_content,
            frontmatter=fm,
            title=f"lore: negate {key}",
            body=f"Auto-generated by lore negate_knowledge: {reason}",
        )
        if pr_url is not None and not policy.stores_locally:
            return {"key": key, "negated": True, "pr_url": pr_url}

        try:
            store.negate(key, reason, level=policy.level)
        except ValueError as exc:
            return {"error": str(exc)}

        return {"key": key, "negated": True, "pr_url": pr_url}

    @server.tool()
    def delete_knowledge(
        key: str,
        level: str = "individual",
    ) -> dict:
        """Delete a knowledge entry from the local store.

        Individual and project entries are deleted locally. Shared entries
        (level 2+) must be deleted via a PR to the knowledge repo.

        Args:
            key: The knowledge key to delete.
            level: Target level — 'individual', 'project', or a configured
                hierarchy level name.

        Returns:
            Confirmation of deletion, or error for shared entries.
        """
        policy = _resolve_level(level)
        _assert_writable(level, policy.writable)
        store = _get_store()
        existing = store.get_by_key_and_level(key, policy.level)
        if existing is None:
            other = store.get(key)
            if other is not None and other.level not in IMPLICIT_LEVELS:
                return {"error": _SHARED_DELETE_ERR}
            return {"error": f"Key not found: '{key}' at level '{level}'"}

        if not policy.locally_deletable:
            return {"error": _SHARED_DELETE_ERR}

        store.delete(key, reason="deleted via MCP", actor="mcp", level=policy.level)
        return {"key": key, "deleted": True}

    return server
