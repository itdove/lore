from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from lore.store.base import KnowledgeEntry, StoreBackend

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS knowledge (
    id               TEXT PRIMARY KEY,
    key              TEXT NOT NULL,
    value            TEXT NOT NULL,
    tags             TEXT,
    level            INTEGER NOT NULL,
    level_name       TEXT,
    locked           BOOLEAN DEFAULT FALSE,
    conflict_with    TEXT,
    conflict_status  TEXT,
    repo_url         TEXT,
    repo_branch      TEXT,
    ingested_from    TEXT,
    provenance       TEXT,
    times_seen       INTEGER DEFAULT 1,
    projects         TEXT,
    embedding        BLOB,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_history (
    id               TEXT PRIMARY KEY,
    knowledge_id     TEXT NOT NULL REFERENCES knowledge(id),
    action           TEXT NOT NULL,
    previous_value   TEXT,
    actor            TEXT,
    reason           TEXT,
    timestamp        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    key, value, tags, content=knowledge, content_rowid=rowid
);

CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
    INSERT INTO knowledge_fts(rowid, key, value, tags)
    VALUES (new.rowid, new.key, new.value, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, key, value, tags)
    VALUES ('delete', old.rowid, old.key, old.value, old.tags);
    INSERT INTO knowledge_fts(rowid, key, value, tags)
    VALUES (new.rowid, new.key, new.value, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, key, value, tags)
    VALUES ('delete', old.rowid, old.key, old.value, old.tags);
END;
"""

_KNOWLEDGE_COLUMNS = [
    "id",
    "key",
    "value",
    "tags",
    "level",
    "level_name",
    "locked",
    "conflict_with",
    "conflict_status",
    "repo_url",
    "repo_branch",
    "ingested_from",
    "provenance",
    "times_seen",
    "projects",
    "embedding",
    "created_at",
    "updated_at",
]


def create_schema(
    db_path_or_conn: str | sqlite3.Connection,
) -> sqlite3.Connection:
    if isinstance(db_path_or_conn, sqlite3.Connection):
        conn = db_path_or_conn
    else:
        conn = sqlite3.connect(db_path_or_conn)
        if db_path_or_conn != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript(_SCHEMA_SQL)
    return conn


class SQLiteStore(StoreBackend):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def _row_to_entry(self, row: sqlite3.Row) -> KnowledgeEntry:
        return KnowledgeEntry(
            id=row["id"],
            key=row["key"],
            value=row["value"],
            tags=row["tags"],
            level=row["level"],
            level_name=row["level_name"],
            locked=bool(row["locked"]),
            conflict_with=row["conflict_with"],
            conflict_status=row["conflict_status"],
            repo_url=row["repo_url"],
            repo_branch=row["repo_branch"],
            ingested_from=row["ingested_from"],
            provenance=row["provenance"],
            times_seen=row["times_seen"],
            projects=row["projects"],
            embedding=row["embedding"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _log_history(
        self,
        knowledge_id: str,
        action: str,
        previous_value: str | None = None,
        actor: str | None = None,
        reason: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO knowledge_history (id, knowledge_id, action, "
            "previous_value, actor, reason) VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, knowledge_id, action, previous_value, actor, reason),
        )

    def store(self, entry: KnowledgeEntry) -> str:
        entry_id = entry.id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        created = entry.created_at or now
        updated = entry.updated_at or now

        placeholders = ", ".join("?" for _ in _KNOWLEDGE_COLUMNS)
        cols = ", ".join(_KNOWLEDGE_COLUMNS)
        self._conn.execute(
            f"INSERT INTO knowledge ({cols}) VALUES ({placeholders})",
            (
                entry_id,
                entry.key,
                entry.value,
                entry.tags,
                entry.level,
                entry.level_name,
                entry.locked,
                entry.conflict_with,
                entry.conflict_status,
                entry.repo_url,
                entry.repo_branch,
                entry.ingested_from,
                entry.provenance,
                entry.times_seen,
                entry.projects,
                entry.embedding,
                created,
                updated,
            ),
        )
        self._log_history(entry_id, "created")
        self._conn.commit()
        return entry_id

    def query_fts(
        self,
        topic: str,
        limit: int = 10,
        filter_levels: list[int] | None = None,
        filter_repos: list[tuple[str, str]] | None = None,
    ) -> list[KnowledgeEntry]:
        conditions = [
            "knowledge_fts MATCH ?",
            "(k.conflict_with IS NULL OR k.conflict_status = 'active')",
        ]
        params: list = [topic]

        if filter_levels is not None:
            levels = sorted(set(filter_levels) | {0})
            placeholders = ", ".join("?" for _ in levels)
            conditions.append(f"k.level IN ({placeholders})")
            params.extend(levels)

        if filter_repos is not None:
            repo_clauses = ["k.level = 0"]
            for repo_url, repo_branch in filter_repos:
                repo_clauses.append("(k.repo_url = ? AND k.repo_branch = ?)")
                params.extend([repo_url, repo_branch])
            conditions.append(f"({' OR '.join(repo_clauses)})")

        where = " AND ".join(conditions)
        params.append(limit)

        sql = (
            f"SELECT k.* FROM knowledge k "
            f"JOIN knowledge_fts ON knowledge_fts.rowid = k.rowid "
            f"WHERE {where} "
            f"ORDER BY rank "
            f"LIMIT ?"
        )

        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get(self, key: str) -> KnowledgeEntry | None:
        row = self._conn.execute(
            "SELECT * FROM knowledge WHERE key = ? LIMIT 1", (key,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def update(self, key: str, value: str, reason: str, actor: str) -> None:
        row = self._conn.execute(
            "SELECT id, value FROM knowledge WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            raise KeyError(key)

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE knowledge SET value = ?, updated_at = ? WHERE key = ?",
            (value, now, key),
        )
        self._log_history(
            row["id"],
            "updated",
            previous_value=row["value"],
            actor=actor,
            reason=reason,
        )
        self._conn.commit()

    def delete(self, key: str, reason: str, actor: str) -> None:
        row = self._conn.execute(
            "SELECT id, value FROM knowledge WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            raise KeyError(key)

        self._log_history(
            row["id"],
            "deleted",
            previous_value=row["value"],
            actor=actor,
            reason=reason,
        )
        self._conn.execute("DELETE FROM knowledge WHERE key = ?", (key,))
        self._conn.commit()

    def list_entries(
        self, tag: str | None = None, level: int | None = None
    ) -> list[KnowledgeEntry]:
        conditions = []
        params: list = []

        if tag is not None:
            conditions.append("tags LIKE ?")
            params.append(f"%{tag}%")

        if level is not None:
            conditions.append("level = ?")
            params.append(level)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._conn.execute(
            f"SELECT * FROM knowledge{where} ORDER BY level ASC, key ASC", params
        ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def list_conflicts(self) -> list[KnowledgeEntry]:
        rows = self._conn.execute(
            "SELECT * FROM knowledge WHERE conflict_with IS NOT NULL ORDER BY key ASC"
        ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def health(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]

        level_rows = self._conn.execute(
            "SELECT level, COUNT(*) FROM knowledge GROUP BY level"
        ).fetchall()
        entries_by_level = {row[0]: row[1] for row in level_rows}

        conflict_count = self._conn.execute(
            "SELECT COUNT(*) FROM knowledge WHERE conflict_with IS NOT NULL"
        ).fetchone()[0]

        oldest = self._conn.execute("SELECT MIN(updated_at) FROM knowledge").fetchone()[
            0
        ]

        newest = self._conn.execute("SELECT MAX(updated_at) FROM knowledge").fetchone()[
            0
        ]

        return {
            "total_entries": total,
            "entries_by_level": entries_by_level,
            "conflict_count": conflict_count,
            "oldest_entry": oldest,
            "newest_entry": newest,
        }
