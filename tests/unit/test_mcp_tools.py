from __future__ import annotations

import pytest

from lore.store.base import KnowledgeEntry
from lore.store.sqlite import SQLiteStore, create_schema


@pytest.fixture
def store():
    conn = create_schema(":memory:")
    return SQLiteStore(conn)


def _make_entry(**kwargs):
    defaults = {"key": "test:domain:slug", "value": "test value", "level": 0}
    defaults.update(kwargs)
    return KnowledgeEntry(**defaults)


# --- helpers to import tool functions via server ---


@pytest.fixture
def tools(monkeypatch, store):
    """Patch _get_store so MCP tools use our in-memory store."""
    import lore.mcp.server as srv

    monkeypatch.setattr(srv, "_get_store", lambda: store)

    server = srv.create_server()
    tool_map = {}
    for tool in server._tool_manager._tools.values():
        tool_map[tool.name] = tool.fn
    return tool_map


# =====================================================================
# AC: query_knowledge returns FTS-ranked results
# =====================================================================


def test_query_knowledge_basic(tools, store):
    store.store(_make_entry(key="python:json", value="JSON parsing library"))
    store.store(_make_entry(key="python:csv", value="CSV file handling"))

    result = tools["query_knowledge"](topic="JSON")
    assert len(result["results"]) == 1
    assert result["results"][0]["key"] == "python:json"


def test_query_knowledge_multiple_results(tools, store):
    store.store(_make_entry(key="k1", value="search topic alpha"))
    store.store(_make_entry(key="k2", value="search topic beta"))

    result = tools["query_knowledge"](topic="search topic")
    assert len(result["results"]) == 2


# =====================================================================
# AC: Overridden conflict entries excluded
# =====================================================================


def test_query_excludes_overridden_conflicts(tools, store):
    store.store(
        _make_entry(
            key="k1",
            value="search term",
            conflict_with="other",
            conflict_status="overridden",
        )
    )
    result = tools["query_knowledge"](topic="search term")
    assert len(result["results"]) == 0


def test_query_includes_active_conflicts(tools, store):
    store.store(
        _make_entry(
            key="k1",
            value="search term",
            conflict_with="other",
            conflict_status="active",
        )
    )
    result = tools["query_knowledge"](topic="search term")
    assert len(result["results"]) == 1


# =====================================================================
# AC: Priority resolution (highest priority wins)
# =====================================================================


def test_priority_resolution_highest_wins(tools, store):
    store.store(
        _make_entry(key="shared:key", value="low priority", level=0, level_name="user")
    )
    store.store(
        _make_entry(key="shared:key", value="high priority", level=2, level_name="org")
    )

    result = tools["query_knowledge"](topic="priority")
    assert len(result["results"]) == 1
    assert result["results"][0]["value"] == "high priority"
    assert result["results"][0]["level"] == 2


# =====================================================================
# AC: Locked entries always win
# =====================================================================


def test_locked_entry_wins_over_higher_level(tools, store):
    store.store(_make_entry(key="cfg:key", value="locked value", level=0, locked=True))
    store.store(
        _make_entry(key="cfg:key", value="unlocked higher", level=3, locked=False)
    )

    result = tools["query_knowledge"](topic="value")
    assert len(result["results"]) == 1
    assert result["results"][0]["value"] == "locked value"
    assert result["results"][0]["locked"] is True


def test_unlocked_does_not_beat_locked(tools, store):
    store.store(_make_entry(key="cfg:key", value="locked low", level=1, locked=True))
    store.store(
        _make_entry(key="cfg:key", value="unlocked high", level=5, locked=False)
    )

    result = tools["query_knowledge"](topic="locked OR unlocked")
    assert len(result["results"]) == 1
    assert result["results"][0]["locked"] is True


# =====================================================================
# AC: Level filter works
# =====================================================================


def test_query_level_filter(tools, store):
    store.store(_make_entry(key="k0", value="search term", level=0))
    store.store(_make_entry(key="k1", value="search term", level=1))
    store.store(_make_entry(key="k2", value="search term", level=2))

    result = tools["query_knowledge"](topic="search term", level="1")
    keys = {r["key"] for r in result["results"]}
    assert "k0" in keys  # level 0 always included
    assert "k1" in keys
    assert "k2" not in keys


# =====================================================================
# AC: LLM synthesis when configured / raw when "none"
# =====================================================================


def test_synthesized_null_when_llm_none(tools, store, monkeypatch):
    store.store(_make_entry(key="k1", value="some content"))

    import lore.mcp.server as srv
    from lore.config.models import GlobalConfig, LLMConfig

    cfg = GlobalConfig(llm=LLMConfig(provider="none"))
    monkeypatch.setattr(srv, "get_global_config", lambda: cfg)

    result = tools["query_knowledge"](topic="content")
    assert result["synthesized"] is None


def test_synthesized_placeholder_when_llm_configured(tools, store, monkeypatch):
    store.store(_make_entry(key="k1", value="some content"))

    import lore.mcp.server as srv
    from lore.config.models import GlobalConfig, LLMConfig

    cfg = GlobalConfig(llm=LLMConfig(provider="openai", model="gpt-4o-mini"))
    monkeypatch.setattr(srv, "get_global_config", lambda: cfg)

    result = tools["query_knowledge"](topic="content")
    # synthesis not yet wired, returns None as placeholder
    assert result["synthesized"] is None
    assert len(result["results"]) >= 1


# =====================================================================
# AC: list_knowledge supports tag + level filters
# =====================================================================


def test_list_knowledge_no_filters(tools, store):
    store.store(_make_entry(key="k1", value="val1"))
    store.store(_make_entry(key="k2", value="val2"))

    result = tools["list_knowledge"]()
    assert len(result["entries"]) == 2


def test_list_knowledge_filter_by_tag(tools, store):
    store.store(_make_entry(key="k1", tags="python,stdlib"))
    store.store(_make_entry(key="k2", tags="rust,systems"))

    result = tools["list_knowledge"](tag="python")
    assert len(result["entries"]) == 1
    assert result["entries"][0]["key"] == "k1"


def test_list_knowledge_filter_by_level(tools, store):
    store.store(_make_entry(key="k1", level=0))
    store.store(_make_entry(key="k2", level=1))

    result = tools["list_knowledge"](level="0")
    assert len(result["entries"]) == 1
    assert result["entries"][0]["key"] == "k1"


def test_list_knowledge_combined_filters(tools, store):
    store.store(_make_entry(key="k1", level=0, tags="python"))
    store.store(_make_entry(key="k2", level=1, tags="python"))
    store.store(_make_entry(key="k3", level=0, tags="rust"))

    result = tools["list_knowledge"](tag="python", level="0")
    assert len(result["entries"]) == 1
    assert result["entries"][0]["key"] == "k1"


# =====================================================================
# AC: list_knowledge with include_history=True returns history
# =====================================================================


def test_list_knowledge_include_history(tools, store):
    store.store(_make_entry(key="k1", value="v1"))
    store.update("k1", "v2", reason="improved", actor="user1")

    result = tools["list_knowledge"](include_history=True)
    assert len(result["entries"]) == 1
    entry = result["entries"][0]
    assert "history" in entry
    assert len(entry["history"]) >= 2  # created + updated
    actions = [h["action"] for h in entry["history"]]
    assert "created" in actions
    assert "updated" in actions


def test_list_knowledge_no_history_by_default(tools, store):
    store.store(_make_entry(key="k1", value="v1"))

    result = tools["list_knowledge"]()
    assert "history" not in result["entries"][0]


# =====================================================================
# AC: list_conflicts returns both sides linked
# =====================================================================


def test_list_conflicts_empty(tools, store):
    store.store(_make_entry(key="k1"))
    result = tools["list_conflicts"]()
    assert result["conflicts"] == []


def test_list_conflicts_both_sides(tools, store):
    id1 = store.store(_make_entry(key="config:timeout", value="30s"))
    store.store(
        _make_entry(
            key="config:timeout",
            value="60s",
            conflict_with=id1,
            conflict_status="active",
        )
    )

    result = tools["list_conflicts"]()
    assert len(result["conflicts"]) == 1

    conflict = result["conflicts"][0]
    assert conflict["entry"]["value"] == "60s"
    assert conflict["conflicting_entry"] is not None
    assert conflict["conflicting_entry"]["value"] == "30s"
    assert conflict["shared_key_pattern"] == "config:timeout"


# =====================================================================
# AC: health_check returns all stats
# =====================================================================


def test_health_check_empty(tools, store):
    result = tools["health_check"]()
    assert result["total"] == 0
    assert result["per_level"] == {}
    assert result["conflicts"] == 0
    assert result["stale_count"] == 0
    assert result["last_sync"] == {}


def test_health_check_with_data(tools, store):
    store.store(_make_entry(key="k1", level=0))
    store.store(_make_entry(key="k2", level=0))
    store.store(_make_entry(key="k3", level=1))

    result = tools["health_check"]()
    assert result["total"] == 3
    assert result["per_level"][0] == 2
    assert result["per_level"][1] == 1


def test_health_check_conflicts(tools, store):
    id1 = store.store(_make_entry(key="k1"))
    store.store(_make_entry(key="k2", conflict_with=id1, conflict_status="active"))

    result = tools["health_check"]()
    assert result["conflicts"] == 1


def test_health_check_stale_count(tools, store):
    store.store(_make_entry(key="k1"))
    # Manually set updated_at to 100 days ago
    store._conn.execute(
        "UPDATE knowledge SET updated_at = datetime('now', '-100 days') "
        "WHERE key = 'k1'"
    )
    store._conn.commit()

    result = tools["health_check"]()
    assert result["stale_count"] == 1


# =====================================================================
# get_history on SQLiteStore
# =====================================================================


def test_get_history(store):
    entry_id = store.store(_make_entry(key="k1", value="v1"))
    store.update("k1", "v2", reason="fix", actor="user")

    history = store.get_history(entry_id)
    assert len(history) == 2
    assert history[0].action == "created"
    assert history[1].action == "updated"
    assert history[1].previous_value == "v1"
    assert history[1].actor == "user"
    assert history[1].reason == "fix"


def test_get_history_empty(store):
    assert store.get_history("nonexistent") == []
