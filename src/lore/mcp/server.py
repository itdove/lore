from __future__ import annotations

import importlib.resources
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from lore.config.manager import get_global_config
from lore.store import get_store as _create_store
from lore.store.base import KnowledgeEntry
from lore.store.priority import resolve_priority
from lore.store.sqlite import SQLiteStore


def _load_lore_instructions() -> str:
    lore_md = Path(".lore/LORE.md")
    if lore_md.exists():
        return lore_md.read_text()
    return importlib.resources.read_text("lore.mcp.skills", "LORE.md")


_store_instance: SQLiteStore | None = None


def _get_store() -> SQLiteStore:
    global _store_instance
    if _store_instance is not None:
        return _store_instance
    _store_instance = _create_store()
    return _store_instance


def _entry_to_dict(entry: KnowledgeEntry) -> dict:
    d = entry.__dict__.copy()
    d.pop("embedding", None)
    return d


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
        if cfg.llm.provider != "none" and results:
            # LLM synthesis placeholder — will be wired in a future issue
            pass

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

    return server
