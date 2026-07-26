from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from lore.ingest.base import LoreIngester
from lore.ingest.reasonsforge import ReasonsForgeIngester
from lore.store.sqlite import SQLiteStore, create_schema


def _make_store():
    return SQLiteStore(create_schema(":memory:"))


def _create_reasons_db(path, tables=None):
    db_path = path / "reasons.db"
    conn = sqlite3.connect(str(db_path))
    if tables is None:
        tables = {
            "decisions": [
                ("id", "TEXT PRIMARY KEY"),
                ("key", "TEXT"),
                ("summary", "TEXT"),
                ("tags", "TEXT"),
                ("created_at", "TIMESTAMP"),
            ]
        }
    for table_name, columns in tables.items():
        cols_sql = ", ".join(f"{n} {t}" for n, t in columns)
        conn.execute(f"CREATE TABLE {table_name} ({cols_sql})")
    conn.commit()
    return conn, db_path


def test_is_lore_ingester(tmp_path):
    ing = ReasonsForgeIngester(_make_store(), tmp_path)
    assert isinstance(ing, LoreIngester)


def test_detect_with_db(tmp_path):
    _create_reasons_db(tmp_path)
    ing = ReasonsForgeIngester(_make_store(), tmp_path)
    assert ing.detect(tmp_path) is True


def test_detect_without_db(tmp_path):
    ing = ReasonsForgeIngester(_make_store(), tmp_path)
    assert ing.detect(tmp_path) is False


def test_extract_decisions(tmp_path):
    conn, _ = _create_reasons_db(tmp_path)
    conn.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
        ("d1", "auth:jwt", "Use JWT for auth", "auth,security", "2026-07-01T00:00:00"),
    )
    conn.commit()
    conn.close()

    ing = ReasonsForgeIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert len(entries) == 1
    assert entries[0].key == "auth:jwt"
    assert entries[0].value == "Use JWT for auth"
    assert entries[0].tags == "auth,security"
    assert entries[0].ingested_from == "reasonsforge"


def test_extract_with_since(tmp_path):
    conn, _ = _create_reasons_db(tmp_path)
    conn.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
        ("d1", "old-entry", "Old decision", None, "2026-01-01T00:00:00"),
    )
    conn.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
        ("d2", "new-entry", "New decision", None, "2026-07-01T00:00:00"),
    )
    conn.commit()
    conn.close()

    ing = ReasonsForgeIngester(_make_store(), tmp_path)
    entries = ing.extract_delta(since=datetime(2026, 6, 1))
    assert len(entries) == 1
    assert entries[0].key == "decisions:new-entry"


def test_extract_empty_db(tmp_path):
    _create_reasons_db(tmp_path)
    ing = ReasonsForgeIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert entries == []


def test_provenance_set(tmp_path):
    conn, _ = _create_reasons_db(tmp_path)
    conn.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
        ("d1", "test:prov", "Provenance test", None, None),
    )
    conn.commit()
    conn.close()

    ing = ReasonsForgeIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    prov = json.loads(entries[0].provenance)
    assert prov["source"] == "reasons.db"
    assert prov["table"] == "decisions"
    assert prov["row_id"] == "d1"


def test_flexible_schema_discovery(tmp_path):
    tables = {
        "patterns": [
            ("id", "TEXT"),
            ("title", "TEXT"),
            ("description", "TEXT"),
        ]
    }
    conn, _ = _create_reasons_db(tmp_path, tables)
    conn.execute(
        "INSERT INTO patterns VALUES (?, ?, ?)",
        ("p1", "singleton", "Use singleton pattern for DB connections"),
    )
    conn.commit()
    conn.close()

    ing = ReasonsForgeIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert len(entries) == 1
    assert "singleton" in entries[0].key


def test_skips_invalid_keys(tmp_path):
    conn, _ = _create_reasons_db(tmp_path)
    conn.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
        ("d1", "has spaces invalid!", "Bad key", None, None),
    )
    conn.commit()
    conn.close()

    ing = ReasonsForgeIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert entries == []


def test_skips_empty_values(tmp_path):
    conn, _ = _create_reasons_db(tmp_path)
    conn.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
        ("d1", "empty:val", "", None, None),
    )
    conn.commit()
    conn.close()

    ing = ReasonsForgeIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert entries == []


def test_key_gets_table_prefix(tmp_path):
    conn, _ = _create_reasons_db(tmp_path)
    conn.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
        ("d1", "simple-key", "A simple key without colon", None, None),
    )
    conn.commit()
    conn.close()

    ing = ReasonsForgeIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert entries[0].key == "decisions:simple-key"


def test_full_pipeline(tmp_path):
    conn, _ = _create_reasons_db(tmp_path)
    conn.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
        ("d1", "test:pipeline", "Pipeline test", "test", None),
    )
    conn.commit()
    conn.close()

    store = _make_store()
    ing = ReasonsForgeIngester(store, tmp_path)
    entries = ing.extract_delta()
    ing.load(entries)

    stored = store.get("test:pipeline")
    assert stored is not None
    assert stored.value == "Pipeline test"
