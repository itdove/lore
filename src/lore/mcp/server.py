from __future__ import annotations

import importlib.resources
from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from lore.config.manager import get_global_config
from lore.config.utils import db_path
from lore.store.base import KnowledgeEntry
from lore.store.priority import resolve_priority
from lore.store.sqlite import SQLiteStore, create_schema


def _load_lore_instructions() -> str:
    lore_md = Path(".lore/LORE.md")
    if lore_md.exists():
        return lore_md.read_text()
    return importlib.resources.read_text("lore.mcp.skills", "LORE.md")


def _get_store() -> SQLiteStore:
    cfg = get_global_config()
    path = cfg.store.path or str(db_path())
    conn = create_schema(path)
    return SQLiteStore(conn)


def _entry_to_dict(entry: KnowledgeEntry) -> dict:
    d = asdict(entry)
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

        results = [
            {
                "key": e.key,
                "value": e.value,
                "level": e.level,
                "level_name": e.level_name,
                "priority": e.level,
                "locked": e.locked,
                "tags": e.tags,
                "times_seen": e.times_seen,
            }
            for e in resolved
        ]

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
                d["history"] = [asdict(h) for h in history]
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
                row = store._conn.execute(
                    "SELECT * FROM knowledge WHERE id = ?",
                    (entry.conflict_with,),
                ).fetchone()
                if row:
                    conflicting_entry = _entry_to_dict(store._row_to_entry(row))

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

        stale_count = store._conn.execute(
            "SELECT COUNT(*) FROM knowledge "
            "WHERE updated_at < datetime('now', '-90 days')"
        ).fetchone()[0]

        return {
            "total": health["total_entries"],
            "per_level": health["entries_by_level"],
            "conflicts": health["conflict_count"],
            "stale_count": stale_count,
            "last_sync": {},
        }

    return server
