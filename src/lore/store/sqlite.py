from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from lore.store.base import HistoryRecord, KnowledgeEntry, StoreBackend

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
        d = dict(row)
        d["locked"] = bool(d["locked"])
        return KnowledgeEntry(**d)

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

    def _insert_entry(
        self,
        entry: KnowledgeEntry,
        entry_id: str,
        created_at: str,
        updated_at: str,
    ) -> None:
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
                created_at,
                updated_at,
            ),
        )

    def store(self, entry: KnowledgeEntry) -> str:
        entry_id = entry.id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        created = entry.created_at or now
        updated = entry.updated_at or now

        self._insert_entry(entry, entry_id, created, updated)
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

        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []
        return [self._row_to_entry(row) for row in rows]

    def get(self, key: str) -> KnowledgeEntry | None:
        row = self._conn.execute(
            "SELECT * FROM knowledge WHERE key = ? LIMIT 1", (key,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def get_by_id(self, entry_id: str) -> KnowledgeEntry | None:
        row = self._conn.execute(
            "SELECT * FROM knowledge WHERE id = ? LIMIT 1", (entry_id,)
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

    def get_history(self, knowledge_id: str) -> list[HistoryRecord]:
        rows = self._conn.execute(
            "SELECT * FROM knowledge_history WHERE knowledge_id = ? "
            "ORDER BY timestamp ASC",
            (knowledge_id,),
        ).fetchall()
        return [
            HistoryRecord(
                id=row["id"],
                knowledge_id=row["knowledge_id"],
                action=row["action"],
                previous_value=row["previous_value"],
                actor=row["actor"],
                reason=row["reason"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    def get_by_source(
        self, key: str, repo_url: str, repo_branch: str
    ) -> KnowledgeEntry | None:
        row = self._conn.execute(
            "SELECT * FROM knowledge "
            "WHERE key = ? AND repo_url = ? AND repo_branch = ?",
            (key, repo_url, repo_branch),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def sync_upsert(self, entry: KnowledgeEntry) -> tuple[str, str]:
        existing = self.get_by_source(entry.key, entry.repo_url, entry.repo_branch)
        now = datetime.now(timezone.utc).isoformat()

        if existing is None:
            entry_id = entry.id or uuid.uuid4().hex
            created = entry.created_at or now
            self._insert_entry(entry, entry_id, created, now)
            self._log_history(entry_id, "created")
            self._conn.commit()
            return entry_id, "created"

        entry_id = existing.id
        self._conn.execute(
            "UPDATE knowledge SET value = ?, tags = ?, level = ?, "
            "level_name = ?, locked = ?, ingested_from = ?, provenance = ?, "
            "times_seen = ?, projects = ?, updated_at = ? "
            "WHERE key = ? AND repo_url = ? AND repo_branch = ?",
            (
                entry.value,
                entry.tags,
                entry.level,
                entry.level_name,
                entry.locked,
                entry.ingested_from,
                entry.provenance,
                entry.times_seen,
                entry.projects,
                now,
                entry.key,
                entry.repo_url,
                entry.repo_branch,
            ),
        )
        self._log_history(entry_id, "updated", previous_value=existing.value)
        self._conn.commit()
        return entry_id, "updated"

    def list_by_repo(self, repo_url: str, repo_branch: str) -> list[KnowledgeEntry]:
        rows = self._conn.execute(
            "SELECT * FROM knowledge WHERE repo_url = ? AND repo_branch = ?",
            (repo_url, repo_branch),
        ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def delete_by_source(
        self,
        key: str,
        repo_url: str,
        repo_branch: str,
        reason: str,
        actor: str,
    ) -> None:
        row = self._conn.execute(
            "SELECT id, value FROM knowledge "
            "WHERE key = ? AND repo_url = ? AND repo_branch = ?",
            (key, repo_url, repo_branch),
        ).fetchone()
        if row is None:
            raise KeyError(key)

        self._log_history(
            row["id"],
            "synced_out",
            previous_value=row["value"],
            actor=actor,
            reason=reason,
        )
        self._conn.execute(
            "DELETE FROM knowledge "
            "WHERE key = ? AND repo_url = ? AND repo_branch = ?",
            (key, repo_url, repo_branch),
        )
        self._conn.commit()

    def list_entries(
        self, tag: str | None = None, level: int | None = None
    ) -> list[KnowledgeEntry]:
        conditions = []
        params: list = []

        if tag is not None:
            escaped = tag.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("(',' || tags || ',') LIKE ? ESCAPE '\\'")
            params.append(f"%,{escaped},%")

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

    def delete_promoted_locals(self) -> int:
        rows = self._conn.execute(
            "SELECT * FROM knowledge WHERE level = 0 "
            "AND key IN (SELECT DISTINCT key FROM knowledge WHERE level > 0)"
        ).fetchall()
        count = 0
        for row in rows:
            self._log_history(
                row["id"],
                "synced_out",
                previous_value=row["value"],
                actor="sync",
                reason="promoted to shared level",
            )
            self._conn.execute("DELETE FROM knowledge WHERE id = ?", (row["id"],))
            count += 1
        if count:
            self._conn.commit()
        return count

    def health(self) -> dict:
        row = self._conn.execute(
            "SELECT "
            "COUNT(*) AS total, "
            "COUNT(CASE WHEN conflict_with IS NOT NULL THEN 1 END) AS conflicts, "
            "COUNT(CASE WHEN updated_at < datetime('now', '-90 days') "
            "THEN 1 END) AS stale, "
            "MIN(updated_at) AS oldest, "
            "MAX(updated_at) AS newest "
            "FROM knowledge"
        ).fetchone()

        level_rows = self._conn.execute(
            "SELECT level, COUNT(*) FROM knowledge GROUP BY level"
        ).fetchall()

        return {
            "total_entries": row[0],
            "entries_by_level": {r[0]: r[1] for r in level_rows},
            "conflict_count": row[1],
            "oldest_entry": row[3],
            "newest_entry": row[4],
            "stale_count": row[2],
        }
