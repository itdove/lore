from __future__ import annotations

import json
from datetime import datetime

from lore.ingest.base import LoreIngester
from lore.ingest.openwolf import OpenWolfIngester
from lore.store.sqlite import SQLiteStore, create_schema


def _make_store():
    return SQLiteStore(create_schema(":memory:"))


def _write_cerebrum(wolf_dir, content):
    wolf_dir.mkdir(parents=True, exist_ok=True)
    (wolf_dir / "cerebrum.md").write_text(content)


def _write_buglog(wolf_dir, bugs):
    wolf_dir.mkdir(parents=True, exist_ok=True)
    (wolf_dir / "buglog.json").write_text(json.dumps({"version": 1, "bugs": bugs}))


def test_is_lore_ingester(tmp_path):
    ing = OpenWolfIngester(_make_store(), tmp_path)
    assert isinstance(ing, LoreIngester)


def test_detect_with_wolf_dir(tmp_path):
    _write_cerebrum(tmp_path / ".wolf", "# Cerebrum\n## User Preferences\n- pref1")
    ing = OpenWolfIngester(_make_store(), tmp_path)
    assert ing.detect(tmp_path) is True


def test_detect_without_wolf_dir(tmp_path):
    ing = OpenWolfIngester(_make_store(), tmp_path)
    assert ing.detect(tmp_path) is False


def test_detect_wolf_dir_no_cerebrum(tmp_path):
    (tmp_path / ".wolf").mkdir()
    ing = OpenWolfIngester(_make_store(), tmp_path)
    assert ing.detect(tmp_path) is False


def test_extract_preferences(tmp_path):
    _write_cerebrum(
        tmp_path / ".wolf",
        "## User Preferences\n\n- Prefer dark mode\n- Use tabs not spaces\n",
    )
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert len(entries) == 2
    assert all(e.key.startswith("preference:") for e in entries)
    assert entries[0].tags == "preference"


def test_extract_learnings(tmp_path):
    _write_cerebrum(
        tmp_path / ".wolf",
        "## Key Learnings\n\n- **Project:** uses MCPServer for tools\n",
    )
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert len(entries) == 1
    assert entries[0].key.startswith("learning:")


def test_extract_do_not_repeat(tmp_path):
    _write_cerebrum(
        tmp_path / ".wolf",
        "## Do-Not-Repeat\n\n- [2026-07-24] Don't mock the database\n",
    )
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert len(entries) == 1
    assert entries[0].key.startswith("do-not-repeat:")


def test_extract_decisions(tmp_path):
    _write_cerebrum(
        tmp_path / ".wolf",
        "## Decision Log\n\n"
        "- [2026-07-24] **Use git CLI not GitPython.** Simpler.\n",
    )
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert len(entries) == 1
    assert entries[0].key.startswith("decision:")


def test_extract_empty_section(tmp_path):
    _write_cerebrum(tmp_path / ".wolf", "## User Preferences\n\n## Key Learnings\n")
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert entries == []


def test_html_comments_skipped(tmp_path):
    _write_cerebrum(
        tmp_path / ".wolf",
        "## User Preferences\n\n<!-- This is a comment -->\n- Real preference\n",
    )
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert len(entries) == 1
    assert "comment" not in entries[0].value


def test_multi_line_bullet(tmp_path):
    _write_cerebrum(
        tmp_path / ".wolf",
        "## User Preferences\n\n- First line of pref\n  continued on next line\n",
    )
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert len(entries) == 1
    assert "continued" in entries[0].value


def test_since_filter_cerebrum(tmp_path):
    _write_cerebrum(
        tmp_path / ".wolf",
        "## Do-Not-Repeat\n\n"
        "- [2026-01-01] Old mistake\n"
        "- [2026-07-24] Recent mistake\n",
    )
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing.extract_delta(since=datetime(2026, 6, 1))
    assert len(entries) == 1
    assert "Recent" in entries[0].value


def test_extract_buglog(tmp_path):
    _write_buglog(
        tmp_path / ".wolf",
        [
            {
                "id": "bug-001",
                "error_message": "ImportError: no module named foo",
                "root_cause": "Missing dependency",
                "fix": "pip install foo",
                "file": "app.py",
                "tags": ["import", "dependency"],
                "timestamp": "2026-07-24T10:00:00",
            }
        ],
    )
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert len(entries) == 1
    assert entries[0].key == "bug:bug-001"
    assert "ImportError" in entries[0].value
    assert "pip install foo" in entries[0].value
    assert entries[0].tags == "import,dependency"
    assert entries[0].ingested_from == "openwolf"


def test_buglog_empty(tmp_path):
    _write_buglog(tmp_path / ".wolf", [])
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    assert entries == []


def test_buglog_missing_file(tmp_path):
    _write_cerebrum(tmp_path / ".wolf", "## User Preferences\n")
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing._extract_buglog()
    assert entries == []


def test_buglog_since_filter(tmp_path):
    _write_buglog(
        tmp_path / ".wolf",
        [
            {"id": "old", "root_cause": "Old bug", "timestamp": "2026-01-01T00:00:00"},
            {"id": "new", "root_cause": "New bug", "timestamp": "2026-07-24T00:00:00"},
        ],
    )
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing._extract_buglog(since=datetime(2026, 6, 1))
    assert len(entries) == 1
    assert entries[0].key == "bug:new"


def test_provenance_cerebrum(tmp_path):
    _write_cerebrum(tmp_path / ".wolf", "## User Preferences\n\n- Test provenance\n")
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    prov = json.loads(entries[0].provenance)
    assert prov["source"] == "cerebrum.md"
    assert prov["section"] == "User Preferences"
    assert prov["item_index"] == 0


def test_provenance_buglog(tmp_path):
    _write_buglog(
        tmp_path / ".wolf",
        [{"id": "bug-042", "root_cause": "Test provenance"}],
    )
    ing = OpenWolfIngester(_make_store(), tmp_path)
    entries = ing.extract_delta()
    prov = json.loads(entries[0].provenance)
    assert prov["source"] == "buglog.json"
    assert prov["bug_id"] == "bug-042"


def test_slugify_strips_markdown():
    slug = OpenWolfIngester._slugify("**Bold text** with `code`")
    assert "bold" in slug.lower()
    assert "code" in slug.lower()
    assert "*" not in slug
    assert "`" not in slug


def test_slugify_strips_date():
    slug = OpenWolfIngester._slugify("[2026-07-24] Some text here")
    assert "2026" not in slug
    assert "some" in slug.lower()


def test_full_pipeline(tmp_path):
    _write_cerebrum(
        tmp_path / ".wolf",
        "## Key Learnings\n\n- SQLite needs fresh connections in threads\n",
    )
    store = _make_store()
    ing = OpenWolfIngester(store, tmp_path)
    entries = ing.extract_delta()
    ing.load(entries)

    all_entries = store.list_entries()
    assert len(all_entries) == 1
    assert "SQLite" in all_entries[0].value
