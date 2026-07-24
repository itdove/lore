import sqlite3

import pytest

from lore.store.base import KnowledgeEntry, StoreBackend
from lore.store.sqlite import SQLiteStore, create_schema


@pytest.fixture
def store():
    conn = create_schema(":memory:")
    return SQLiteStore(conn)


def _make_entry(**kwargs):
    defaults = {"key": "test:domain:slug", "value": "test value", "level": 0}
    defaults.update(kwargs)
    return KnowledgeEntry(**defaults)


# --- AC1: KnowledgeEntry dataclass ---


def test_knowledge_entry_required_fields():
    entry = KnowledgeEntry(key="k", value="v", level=0)
    assert entry.key == "k"
    assert entry.value == "v"
    assert entry.level == 0


def test_knowledge_entry_defaults():
    entry = KnowledgeEntry(key="k", value="v", level=0)
    assert entry.id == ""
    assert entry.tags is None
    assert entry.level_name is None
    assert entry.locked is False
    assert entry.conflict_with is None
    assert entry.conflict_status is None
    assert entry.repo_url is None
    assert entry.repo_branch is None
    assert entry.ingested_from is None
    assert entry.provenance is None
    assert entry.times_seen == 1
    assert entry.projects is None
    assert entry.embedding is None
    assert entry.created_at is None
    assert entry.updated_at is None


def test_knowledge_entry_all_fields():
    entry = KnowledgeEntry(
        key="k",
        value="v",
        level=1,
        id="abc",
        tags="t1,t2",
        level_name="team",
        locked=True,
        conflict_with="other-id",
        conflict_status="active",
        repo_url="https://github.com/org/repo",
        repo_branch="main",
        ingested_from="git",
        provenance='{"sha": "abc123"}',
        times_seen=5,
        projects="proj1,proj2",
        embedding=b"\x00\x01",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-06-01T00:00:00",
    )
    assert entry.id == "abc"
    assert entry.locked is True
    assert entry.times_seen == 5
    assert entry.embedding == b"\x00\x01"


# --- AC2: StoreBackend ABC ---


def test_store_backend_is_abstract():
    with pytest.raises(TypeError):
        StoreBackend()


def test_sqlite_store_is_store_backend(store):
    assert isinstance(store, StoreBackend)


# --- AC3: SQLite CRUD ---


def test_store_and_get(store):
    entry = _make_entry(key="type:domain:slug", value="hello world")
    entry_id = store.store(entry)
    result = store.get("type:domain:slug")
    assert result is not None
    assert result.id == entry_id
    assert result.key == "type:domain:slug"
    assert result.value == "hello world"
    assert result.level == 0


def test_store_generates_id(store):
    entry = _make_entry()
    entry_id = store.store(entry)
    assert len(entry_id) == 32  # uuid4 hex


def test_store_preserves_given_id(store):
    entry = _make_entry(id="custom-id")
    entry_id = store.store(entry)
    assert entry_id == "custom-id"


def test_store_returns_id(store):
    entry = _make_entry()
    result = store.store(entry)
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_missing_key_returns_none(store):
    assert store.get("nonexistent") is None


def test_update_changes_value(store):
    store.store(_make_entry(key="k1", value="old"))
    store.update("k1", "new", reason="testing", actor="tester")
    result = store.get("k1")
    assert result.value == "new"


def test_update_missing_key_raises(store):
    with pytest.raises(KeyError):
        store.update("missing", "val", "reason", "actor")


def test_delete_removes_entry(store):
    store.store(_make_entry(key="k1"))
    store.delete("k1", reason="cleanup", actor="tester")
    assert store.get("k1") is None


def test_delete_missing_key_raises(store):
    with pytest.raises(KeyError):
        store.delete("missing", "reason", "actor")


# --- AC4: create_schema ---


def test_create_schema_memory():
    conn = create_schema(":memory:")
    assert isinstance(conn, sqlite3.Connection)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {row[0] for row in tables}
    assert "knowledge" in table_names
    assert "knowledge_history" in table_names


def test_create_schema_file_path(tmp_path):
    db_file = str(tmp_path / "test.db")
    conn = create_schema(db_file)
    assert isinstance(conn, sqlite3.Connection)
    assert (tmp_path / "test.db").exists()
    conn.close()


def test_create_schema_connection():
    raw_conn = sqlite3.connect(":memory:")
    conn = create_schema(raw_conn)
    assert conn is raw_conn
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {row[0] for row in tables}
    assert "knowledge" in table_names


def test_create_schema_idempotent():
    conn = create_schema(":memory:")
    create_schema(conn)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [row[0] for row in tables]
    assert table_names.count("knowledge") == 1


# --- AC5: FTS5 BM25 ranking ---


def test_query_fts_basic(store):
    store.store(_make_entry(key="python:stdlib:json", value="JSON parsing library"))
    results = store.query_fts("json")
    assert len(results) == 1
    assert results[0].key == "python:stdlib:json"


def test_query_fts_relevance_ranking(store):
    store.store(
        _make_entry(
            key="other:topic:misc",
            value="something about data",
            tags="json",
        )
    )
    store.store(
        _make_entry(
            key="python:stdlib:json",
            value="json parsing and json serialization library for json data",
        )
    )
    results = store.query_fts("json")
    assert len(results) == 2
    assert results[0].key == "python:stdlib:json"


def test_query_fts_limit(store):
    for i in range(5):
        store.store(_make_entry(key=f"topic:search:{i}", value=f"search result {i}"))
    results = store.query_fts("search", limit=3)
    assert len(results) == 3


def test_query_fts_no_results(store):
    store.store(_make_entry(value="unrelated content"))
    results = store.query_fts("nonexistent_term_xyz")
    assert results == []


def test_query_fts_filter_levels(store):
    store.store(_make_entry(key="k0", value="search term", level=0))
    store.store(_make_entry(key="k1", value="search term", level=1))
    store.store(_make_entry(key="k2", value="search term", level=2))
    results = store.query_fts("search", filter_levels=[1])
    keys = {r.key for r in results}
    assert "k0" in keys  # level 0 always included
    assert "k1" in keys
    assert "k2" not in keys


def test_query_fts_filter_repos(store):
    store.store(_make_entry(key="k0", value="search term", level=0))
    store.store(
        _make_entry(
            key="k1",
            value="search term",
            level=1,
            repo_url="https://github.com/org/repo1",
            repo_branch="main",
        )
    )
    store.store(
        _make_entry(
            key="k2",
            value="search term",
            level=1,
            repo_url="https://github.com/org/repo2",
            repo_branch="dev",
        )
    )
    results = store.query_fts(
        "search",
        filter_repos=[("https://github.com/org/repo1", "main")],
    )
    keys = {r.key for r in results}
    assert "k0" in keys  # level 0 always included
    assert "k1" in keys
    assert "k2" not in keys


def test_query_fts_excludes_overridden_conflicts(store):
    store.store(
        _make_entry(
            key="k1",
            value="search term",
            conflict_with="other",
            conflict_status="overridden",
        )
    )
    results = store.query_fts("search")
    assert results == []


def test_query_fts_includes_active_conflicts(store):
    store.store(
        _make_entry(
            key="k1",
            value="search term",
            conflict_with="other",
            conflict_status="active",
        )
    )
    results = store.query_fts("search")
    assert len(results) == 1


def test_query_fts_includes_no_conflict(store):
    store.store(_make_entry(key="k1", value="search term"))
    results = store.query_fts("search")
    assert len(results) == 1
    assert results[0].conflict_with is None


# --- AC6: FTS triggers ---


def test_fts_sync_on_insert(store):
    store.store(_make_entry(key="new:entry", value="unique content xyz"))
    results = store.query_fts("unique content xyz")
    assert len(results) == 1


def test_fts_sync_on_update(store):
    store.store(_make_entry(key="k1", value="old content abc"))
    store.update("k1", "new content def", reason="test", actor="tester")
    assert store.query_fts("old content abc") == []
    results = store.query_fts("new content def")
    assert len(results) == 1


def test_fts_sync_on_delete(store):
    store.store(_make_entry(key="k1", value="deletable content ghi"))
    store.delete("k1", reason="test", actor="tester")
    assert store.query_fts("deletable content ghi") == []


# --- AC7: History logging ---


def test_history_on_store(store):
    entry_id = store.store(_make_entry(key="k1"))
    rows = store._conn.execute(
        "SELECT * FROM knowledge_history WHERE knowledge_id = ?", (entry_id,)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["action"] == "created"


def test_history_on_update(store):
    entry_id = store.store(_make_entry(key="k1", value="old"))
    store.update("k1", "new", reason="changed", actor="user1")
    rows = store._conn.execute(
        "SELECT * FROM knowledge_history WHERE knowledge_id = ? "
        "AND action = 'updated'",
        (entry_id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["previous_value"] == "old"
    assert rows[0]["actor"] == "user1"
    assert rows[0]["reason"] == "changed"


def test_history_on_delete(store):
    entry_id = store.store(_make_entry(key="k1", value="val"))
    store.delete("k1", reason="removed", actor="admin")
    rows = store._conn.execute(
        "SELECT * FROM knowledge_history WHERE knowledge_id = ? "
        "AND action = 'deleted'",
        (entry_id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["previous_value"] == "val"
    assert rows[0]["actor"] == "admin"
    assert rows[0]["reason"] == "removed"


def test_history_records_actor_and_reason(store):
    entry_id = store.store(_make_entry(key="k1", value="v1"))
    store.update("k1", "v2", reason="refine", actor="bot")
    rows = store._conn.execute(
        "SELECT actor, reason FROM knowledge_history "
        "WHERE knowledge_id = ? AND action = 'updated'",
        (entry_id,),
    ).fetchall()
    assert rows[0]["actor"] == "bot"
    assert rows[0]["reason"] == "refine"


# --- AC8: list_conflicts ---


def test_list_conflicts_empty(store):
    store.store(_make_entry(key="k1"))
    assert store.list_conflicts() == []


def test_list_conflicts_returns_conflicting_entries(store):
    id1 = store.store(_make_entry(key="k1"))
    store.store(
        _make_entry(
            key="k2",
            conflict_with=id1,
            conflict_status="active",
        )
    )
    conflicts = store.list_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0].key == "k2"
    assert conflicts[0].conflict_with == id1


# --- AC9: health ---


def test_health_empty_db(store):
    h = store.health()
    assert h["total_entries"] == 0
    assert h["entries_by_level"] == {}
    assert h["conflict_count"] == 0
    assert h["oldest_entry"] is None
    assert h["newest_entry"] is None


def test_health_with_entries(store):
    store.store(_make_entry(key="k1", level=0))
    store.store(_make_entry(key="k2", level=0))
    store.store(_make_entry(key="k3", level=1))
    h = store.health()
    assert h["total_entries"] == 3
    assert h["entries_by_level"][0] == 2
    assert h["entries_by_level"][1] == 1


def test_health_conflict_count(store):
    id1 = store.store(_make_entry(key="k1"))
    store.store(_make_entry(key="k2", conflict_with=id1, conflict_status="active"))
    h = store.health()
    assert h["conflict_count"] == 1


def test_health_staleness(store):
    store.store(_make_entry(key="k1"))
    h = store.health()
    assert h["oldest_entry"] is not None
    assert h["newest_entry"] is not None


# --- AC10: repo_url and repo_branch ---


def test_store_with_repo_info(store):
    store.store(
        _make_entry(
            key="k1",
            repo_url="https://github.com/org/repo",
            repo_branch="main",
        )
    )
    result = store.get("k1")
    assert result.repo_url == "https://github.com/org/repo"
    assert result.repo_branch == "main"


def test_query_fts_filter_repos_matches(store):
    store.store(
        _make_entry(
            key="k1",
            value="search term",
            level=1,
            repo_url="https://github.com/org/repo",
            repo_branch="main",
        )
    )
    results = store.query_fts(
        "search",
        filter_repos=[("https://github.com/org/repo", "main")],
    )
    assert len(results) == 1
    assert results[0].repo_url == "https://github.com/org/repo"


def test_list_entries_with_repo_info(store):
    store.store(
        _make_entry(
            key="k1",
            repo_url="https://github.com/org/repo",
            repo_branch="dev",
        )
    )
    entries = store.list_entries()
    assert len(entries) == 1
    assert entries[0].repo_url == "https://github.com/org/repo"
    assert entries[0].repo_branch == "dev"


# --- Additional edge cases ---


def test_list_entries_no_filters(store):
    store.store(_make_entry(key="k1"))
    store.store(_make_entry(key="k2"))
    entries = store.list_entries()
    assert len(entries) == 2


def test_list_entries_filter_by_tag(store):
    store.store(_make_entry(key="k1", tags="python,stdlib"))
    store.store(_make_entry(key="k2", tags="rust,systems"))
    entries = store.list_entries(tag="python")
    assert len(entries) == 1
    assert entries[0].key == "k1"


def test_list_entries_filter_by_level(store):
    store.store(_make_entry(key="k1", level=0))
    store.store(_make_entry(key="k2", level=1))
    entries = store.list_entries(level=0)
    assert len(entries) == 1
    assert entries[0].key == "k1"


def test_store_with_all_optional_fields(store):
    entry = KnowledgeEntry(
        key="full:entry",
        value="complete",
        level=2,
        id="my-id",
        tags="a,b",
        level_name="org",
        locked=True,
        conflict_with="other",
        conflict_status="active",
        repo_url="https://example.com",
        repo_branch="dev",
        ingested_from="git",
        provenance='{"sha":"123"}',
        times_seen=3,
        projects="p1,p2",
        embedding=b"\xff",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-06-01T00:00:00",
    )
    store.store(entry)
    result = store.get("full:entry")
    assert result.id == "my-id"
    assert result.tags == "a,b"
    assert result.level_name == "org"
    assert result.locked is True
    assert result.conflict_with == "other"
    assert result.conflict_status == "active"
    assert result.ingested_from == "git"
    assert result.provenance == '{"sha":"123"}'
    assert result.times_seen == 3
    assert result.projects == "p1,p2"
    assert result.embedding == b"\xff"
    assert result.created_at == "2024-01-01T00:00:00"
    assert result.updated_at == "2024-06-01T00:00:00"


def test_locked_field_stored_as_bool(store):
    store.store(_make_entry(key="k1", locked=True))
    result = store.get("k1")
    assert result.locked is True
    assert type(result.locked) is bool


# --- Sync-specific methods ---


def test_get_by_source_found(store):
    store.store(
        _make_entry(key="k1", repo_url="https://github.com/org/r", repo_branch="main")
    )
    result = store.get_by_source("k1", "https://github.com/org/r", "main")
    assert result is not None
    assert result.key == "k1"


def test_get_by_source_not_found(store):
    assert store.get_by_source("k1", "https://github.com/org/r", "main") is None


def test_get_by_source_ignores_different_repo(store):
    store.store(
        _make_entry(key="k1", repo_url="https://github.com/org/r1", repo_branch="main")
    )
    assert store.get_by_source("k1", "https://github.com/org/r2", "main") is None


def test_sync_upsert_insert(store):
    entry = _make_entry(
        key="k1",
        repo_url="https://github.com/org/r",
        repo_branch="main",
    )
    entry_id, action = store.sync_upsert(entry)
    assert action == "created"
    assert len(entry_id) == 32
    result = store.get("k1")
    assert result is not None
    assert result.key == "k1"


def test_sync_upsert_update(store):
    entry = _make_entry(
        key="k1",
        value="old",
        repo_url="https://github.com/org/r",
        repo_branch="main",
    )
    entry_id, _ = store.sync_upsert(entry)
    updated = _make_entry(
        key="k1",
        value="new",
        repo_url="https://github.com/org/r",
        repo_branch="main",
        tags="t1,t2",
    )
    updated_id, action = store.sync_upsert(updated)
    assert action == "updated"
    assert updated_id == entry_id
    result = store.get("k1")
    assert result.value == "new"
    assert result.tags == "t1,t2"


def test_sync_upsert_preserves_id_and_created_at(store):
    entry = _make_entry(
        key="k1",
        repo_url="https://github.com/org/r",
        repo_branch="main",
    )
    entry_id, _ = store.sync_upsert(entry)
    result1 = store.get("k1")
    created_at = result1.created_at

    updated = _make_entry(
        key="k1",
        value="new",
        repo_url="https://github.com/org/r",
        repo_branch="main",
    )
    updated_id, _ = store.sync_upsert(updated)
    result2 = store.get("k1")
    assert updated_id == entry_id
    assert result2.created_at == created_at


def test_sync_upsert_updates_all_fields(store):
    entry = _make_entry(
        key="k1",
        value="v1",
        level=1,
        tags="a",
        locked=False,
        provenance='{"sha":"old"}',
        repo_url="https://github.com/org/r",
        repo_branch="main",
        ingested_from="git",
    )
    store.sync_upsert(entry)
    updated = _make_entry(
        key="k1",
        value="v2",
        level=2,
        level_name="org",
        tags="b,c",
        locked=True,
        provenance='{"sha":"new"}',
        repo_url="https://github.com/org/r",
        repo_branch="main",
        ingested_from="git",
        projects="p1",
    )
    store.sync_upsert(updated)
    result = store.get("k1")
    assert result.value == "v2"
    assert result.level == 2
    assert result.level_name == "org"
    assert result.tags == "b,c"
    assert result.locked is True
    assert result.provenance == '{"sha":"new"}'
    assert result.projects == "p1"


def test_list_by_repo(store):
    store.store(
        _make_entry(key="k1", repo_url="https://github.com/org/r", repo_branch="main")
    )
    store.store(
        _make_entry(key="k2", repo_url="https://github.com/org/r", repo_branch="main")
    )
    store.store(
        _make_entry(
            key="k3", repo_url="https://github.com/org/other", repo_branch="dev"
        )
    )
    results = store.list_by_repo("https://github.com/org/r", "main")
    assert len(results) == 2
    keys = {r.key for r in results}
    assert keys == {"k1", "k2"}


def test_list_by_repo_empty(store):
    assert store.list_by_repo("https://github.com/org/r", "main") == []


def test_delete_by_source(store):
    store.store(
        _make_entry(key="k1", repo_url="https://github.com/org/r", repo_branch="main")
    )
    store.delete_by_source(
        "k1", "https://github.com/org/r", "main", "file removed", "sync"
    )
    assert store.get("k1") is None


def test_delete_by_source_logs_synced_out(store):
    store.store(
        _make_entry(
            key="k1",
            value="val",
            repo_url="https://github.com/org/r",
            repo_branch="main",
        )
    )
    entry = store.get("k1")
    store.delete_by_source("k1", "https://github.com/org/r", "main", "removed", "sync")
    rows = store._conn.execute(
        "SELECT * FROM knowledge_history WHERE knowledge_id = ? "
        "AND action = 'synced_out'",
        (entry.id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["previous_value"] == "val"


def test_delete_by_source_not_found(store):
    with pytest.raises(KeyError):
        store.delete_by_source("missing", "url", "branch", "reason", "actor")
