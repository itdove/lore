from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from lore.ingest.base import LoreIngester
from lore.ingest.registry import register
from lore.store.base import KnowledgeEntry, StoreBackend, validate_key

log = logging.getLogger("lore.ingest")

_KEY_COLUMNS = ("key", "name", "title")
_VALUE_COLUMNS = ("summary", "description", "value", "content")
_TIME_COLUMNS = ("created_at", "updated_at")
_TAG_COLUMN = "tags"


@register
class ReasonsForgeIngester(LoreIngester):
    """Ingest from a ReasonsForge reasons.db SQLite file.

    Schema discovery is flexible — any table with a key-like column
    (key/name/title) and a value-like column (summary/description/value/content)
    will be read. Typical tables: decisions, patterns, conventions.
    """

    name = "reasonsforge"
    triggers = frozenset({"hook", "manual"})
    review_policy = "immediate"

    def __init__(self, store: StoreBackend, project_dir: Path) -> None:
        super().__init__(store, project_dir)
        self._db_path = project_dir / "reasons.db"

    def detect(self, project_dir: Path) -> bool:
        return (project_dir / "reasons.db").is_file()

    def extract_delta(self, since: datetime | None = None) -> list[KnowledgeEntry]:
        if not self._db_path.is_file():
            return []

        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            tables = self._discover_tables(conn)
            entries: list[KnowledgeEntry] = []
            for table, key_col, val_col, tag_col, time_col in tables:
                entries.extend(
                    self._extract_table(
                        conn, table, key_col, val_col, tag_col, time_col, since
                    )
                )
            return entries
        finally:
            conn.close()

    def _discover_tables(
        self, conn: sqlite3.Connection
    ) -> list[tuple[str, str, str, str | None, str | None]]:
        tables = []
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        for (name,) in cursor:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info([{name}])")}
            key_col = next((c for c in _KEY_COLUMNS if c in cols), None)
            val_col = next((c for c in _VALUE_COLUMNS if c in cols), None)
            if key_col and val_col:
                tag_col = _TAG_COLUMN if _TAG_COLUMN in cols else None
                time_col = next((c for c in _TIME_COLUMNS if c in cols), None)
                tables.append((name, key_col, val_col, tag_col, time_col))
        return tables

    def _extract_table(
        self,
        conn: sqlite3.Connection,
        table: str,
        key_col: str,
        val_col: str,
        tag_col: str | None,
        time_col: str | None,
        since: datetime | None,
    ) -> list[KnowledgeEntry]:
        query = f"SELECT * FROM [{table}]"
        params: list[str] = []
        if since and time_col:
            query += f" WHERE [{time_col}] >= ?"
            params.append(since.isoformat())

        entries: list[KnowledgeEntry] = []
        for row in conn.execute(query, params):
            raw_key = row[key_col]
            if not raw_key:
                continue

            key = str(raw_key).strip().lower().replace(" ", "-")
            if ":" not in key:
                key = f"{table}:{key}"

            if validate_key(key) is not None:
                log.warning("Skipping invalid key: %s (table=%s)", raw_key, table)
                continue

            value = str(row[val_col] or "")
            if not value.strip():
                continue

            tags = str(row[tag_col]) if tag_col and row[tag_col] else None
            row_id = row["id"] if "id" in row.keys() else None

            provenance = json.dumps(
                {
                    "source": "reasons.db",
                    "table": table,
                    "row_id": str(row_id) if row_id else None,
                }
            )

            entries.append(
                KnowledgeEntry(
                    key=key,
                    value=value,
                    level=0,
                    tags=tags,
                    ingested_from="reasonsforge",
                    provenance=provenance,
                )
            )

        return entries
