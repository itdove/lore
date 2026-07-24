from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone

from lore.embedding.base import blob_to_embed, cosine_distance
from lore.store.base import HistoryRecord, KnowledgeEntry, StoreBackend

log = logging.getLogger("lore.store")

_RRF_K = 60

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
    negated          TEXT,
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
    "negated",
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
                entry.negated,
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

    @staticmethod
    def _build_filter(
        filter_levels: list[int] | None,
        filter_repos: list[tuple[str, str]] | None,
        include_negated: bool,
        col_prefix: str = "",
    ) -> tuple[list[str], list]:
        p = f"{col_prefix}." if col_prefix else ""
        conditions = [
            f"({p}conflict_with IS NULL OR {p}conflict_status = 'active')",
        ]
        if not include_negated:
            conditions.append(f"{p}negated IS NULL")
        params: list = []

        if filter_levels is not None:
            levels = sorted(set(filter_levels) | {0})
            placeholders = ", ".join("?" for _ in levels)
            conditions.append(f"{p}level IN ({placeholders})")
            params.extend(levels)

        if filter_repos is not None:
            repo_clauses = [f"{p}level = 0"]
            for repo_url, repo_branch in filter_repos:
                repo_clauses.append(f"({p}repo_url = ? AND {p}repo_branch = ?)")
                params.extend([repo_url, repo_branch])
            conditions.append(f"({' OR '.join(repo_clauses)})")

        return conditions, params

    def query_fts(
        self,
        topic: str,
        limit: int = 10,
        filter_levels: list[int] | None = None,
        filter_repos: list[tuple[str, str]] | None = None,
        include_negated: bool = False,
    ) -> list[KnowledgeEntry]:
        conditions, params = self._build_filter(
            filter_levels, filter_repos, include_negated, col_prefix="k"
        )
        conditions.insert(0, "knowledge_fts MATCH ?")
        params.insert(0, topic)

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

    def get_by_key_and_level(self, key: str, level: int) -> KnowledgeEntry | None:
        row = self._conn.execute(
            "SELECT * FROM knowledge WHERE key = ? AND level = ? LIMIT 1",
            (key, level),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def _key_where(self, key: str, level: int | None) -> tuple[str, list]:
        if level is not None:
            return "WHERE key = ? AND level = ?", [key, level]
        return "WHERE key = ?", [key]

    def update(
        self,
        key: str,
        value: str,
        reason: str,
        actor: str,
        *,
        tags: str | None = None,
        level: int | None = None,
    ) -> None:
        where, where_params = self._key_where(key, level)
        row = self._conn.execute(
            f"SELECT id, value FROM knowledge {where}", where_params
        ).fetchone()
        if row is None:
            raise KeyError(key)

        now = datetime.now(timezone.utc).isoformat()
        set_parts = ["value = ?", "negated = NULL"]
        params: list = [value]
        if tags is not None:
            set_parts.append("tags = ?")
            params.append(tags)
        set_parts.append("updated_at = ?")
        params.append(now)
        params.extend(where_params)
        self._conn.execute(
            f"UPDATE knowledge SET {', '.join(set_parts)} {where}",
            params,
        )
        self._log_history(
            row["id"],
            "updated",
            previous_value=row["value"],
            actor=actor,
            reason=reason,
        )
        self._conn.commit()

    def negate(
        self, key: str, reason: str, *, actor: str = "mcp", level: int | None = None
    ) -> None:
        where, where_params = self._key_where(key, level)
        row = self._conn.execute(
            f"SELECT id, negated, locked FROM knowledge {where}", where_params
        ).fetchone()
        if row is None:
            raise KeyError(key)
        if row["locked"]:
            raise ValueError(f"Cannot negate locked entry '{key}'")

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            f"UPDATE knowledge SET negated = ?, updated_at = ? {where}",
            [reason, now, *where_params],
        )
        self._log_history(
            row["id"],
            "negated",
            actor=actor,
            reason=reason,
            previous_value=row["negated"],
        )
        self._conn.commit()

    def delete(
        self, key: str, reason: str, actor: str, *, level: int | None = None
    ) -> None:
        where, where_params = self._key_where(key, level)
        row = self._conn.execute(
            f"SELECT id, value FROM knowledge {where}", where_params
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
        self._conn.execute(f"DELETE FROM knowledge {where}", where_params)
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

    def sync_upsert(
        self,
        entry: KnowledgeEntry,
        *,
        pre_conflicts: list[KnowledgeEntry] | None = None,
    ) -> tuple[str, str]:
        conflicts = (
            pre_conflicts
            if pre_conflicts is not None
            else self.find_conflicts(entry.key, entry.level)
        )
        for other in conflicts:
            if other.locked and other.level < entry.level:
                return "", "blocked"

        existing = self.get_by_source(entry.key, entry.repo_url, entry.repo_branch)
        now = datetime.now(timezone.utc).isoformat()

        if existing is None:
            entry_id = entry.id or uuid.uuid4().hex
            created = entry.created_at or now
            self._insert_entry(entry, entry_id, created, now)
            self._log_history(entry_id, "created")
            return entry_id, "created"

        entry_id = existing.id
        self._conn.execute(
            "UPDATE knowledge SET value = ?, tags = ?, level = ?, "
            "level_name = ?, locked = ?, ingested_from = ?, provenance = ?, "
            "times_seen = ?, projects = ?, embedding = ?, updated_at = ? "
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
                entry.embedding,
                now,
                entry.key,
                entry.repo_url,
                entry.repo_branch,
            ),
        )
        self._log_history(entry_id, "updated", previous_value=existing.value)
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

    def list_entries(
        self,
        tag: str | None = None,
        level: int | None = None,
        include_negated: bool = False,
    ) -> list[KnowledgeEntry]:
        conditions = []
        params: list = []

        if not include_negated:
            conditions.append("negated IS NULL")

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

    def find_conflicts(self, key: str, level: int) -> list[KnowledgeEntry]:
        rows = self._conn.execute(
            "SELECT * FROM knowledge WHERE key = ? AND level != ?",
            (key, level),
        ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def apply_conflict(self, winner_id: str, loser_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        pairs = [
            (winner_id, loser_id, "active", f"conflicts with {loser_id}"),
            (loser_id, winner_id, "overridden", f"overridden by {winner_id}"),
        ]
        for entry_id, other_id, status, reason in pairs:
            cur = self._conn.execute(
                "UPDATE knowledge SET conflict_with = ?, conflict_status = ?, "
                "updated_at = ? WHERE id = ?",
                (other_id, status, now, entry_id),
            )
            if cur.rowcount:
                self._log_history(entry_id, "conflict_detected", reason=reason)

    def clear_conflict(self, entry_id: str) -> None:
        rows = self._conn.execute(
            "SELECT id FROM knowledge WHERE conflict_with = ?", (entry_id,)
        ).fetchall()
        if not rows:
            return
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE knowledge SET conflict_with = NULL, conflict_status = NULL, "
            "updated_at = ? WHERE conflict_with = ?",
            (now, entry_id),
        )
        for row in rows:
            self._log_history(
                row["id"],
                "conflict_resolved",
                reason=f"counterpart {entry_id} removed",
            )

    def find_conflicts_batch(
        self, keys: set[str], level: int
    ) -> dict[str, list[KnowledgeEntry]]:
        if not keys:
            return {}
        placeholders = ", ".join("?" for _ in keys)
        rows = self._conn.execute(
            f"SELECT * FROM knowledge WHERE key IN ({placeholders}) AND level != ?",
            [*keys, level],
        ).fetchall()
        result: dict[str, list[KnowledgeEntry]] = {}
        for row in rows:
            entry = self._row_to_entry(row)
            result.setdefault(entry.key, []).append(entry)
        return result

    def commit(self) -> None:
        self._conn.commit()

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
        return count

    def query_vector(
        self,
        embedding: list[float],
        limit: int = 10,
        filter_levels: list[int] | None = None,
        filter_repos: list[tuple[str, str]] | None = None,
        include_negated: bool = False,
    ) -> list[tuple[KnowledgeEntry, float]]:
        if not embedding:
            return []
        conditions, params = self._build_filter(
            filter_levels, filter_repos, include_negated
        )
        conditions.insert(0, "embedding IS NOT NULL")

        where = " AND ".join(conditions)
        sql = f"SELECT * FROM knowledge WHERE {where}"

        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            log.warning("Vector search failed: %s", exc)
            return []

        scored = []
        for row in rows:
            entry = self._row_to_entry(row)
            stored = blob_to_embed(row["embedding"])
            dist = cosine_distance(embedding, stored)
            scored.append((entry, dist))

        scored.sort(key=lambda x: x[1])
        return scored[:limit]

    def query_hybrid(
        self,
        topic: str,
        query_embedding: list[float] | None = None,
        limit: int = 10,
        filter_levels: list[int] | None = None,
        filter_repos: list[tuple[str, str]] | None = None,
        include_negated: bool = False,
    ) -> list[KnowledgeEntry]:
        pool = limit * 3
        fts_results = self.query_fts(
            topic,
            limit=pool,
            filter_levels=filter_levels,
            filter_repos=filter_repos,
            include_negated=include_negated,
        )

        if not query_embedding:
            return fts_results[:limit]

        vec_results = self.query_vector(
            query_embedding,
            limit=pool,
            filter_levels=filter_levels,
            filter_repos=filter_repos,
            include_negated=include_negated,
        )

        if not vec_results:
            return fts_results[:limit]

        scores: dict[str, float] = {}
        entries: dict[str, KnowledgeEntry] = {}

        for rank, entry in enumerate(fts_results, start=1):
            eid = entry.id
            scores[eid] = scores.get(eid, 0) + 1.0 / (_RRF_K + rank)
            entries[eid] = entry

        for rank, (entry, _distance) in enumerate(vec_results, start=1):
            eid = entry.id
            scores[eid] = scores.get(eid, 0) + 1.0 / (_RRF_K + rank)
            entries[eid] = entry

        ranked = sorted(scores, key=lambda eid: scores[eid], reverse=True)
        return [entries[eid] for eid in ranked[:limit]]

    def health(self) -> dict:
        row = self._conn.execute(
            "SELECT "
            "COUNT(*) AS total, "
            "COUNT(CASE WHEN conflict_with IS NOT NULL THEN 1 END) AS conflicts, "
            "COUNT(CASE WHEN updated_at < datetime('now', '-90 days') "
            "THEN 1 END) AS stale, "
            "COUNT(CASE WHEN negated IS NOT NULL THEN 1 END) AS negated, "
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
            "stale_count": row[2],
            "negated_count": row[3],
            "oldest_entry": row[4],
            "newest_entry": row[5],
        }
