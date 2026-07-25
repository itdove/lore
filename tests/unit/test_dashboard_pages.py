from __future__ import annotations

import pytest

from lore.dashboard.state import get_dashboard_store, reset_store, validate_key
from lore.store.base import KnowledgeEntry


@pytest.fixture(autouse=True)
def _reset():
    reset_store()
    yield
    reset_store()


class TestCrudScopeEnforcement:
    def test_validate_key_accepts_valid(self):
        assert validate_key("type:domain:slug") is None

    def test_validate_key_rejects_invalid(self):
        assert validate_key("bad-key") is not None

    def test_store_level_zero(self):
        store = get_dashboard_store()
        entry = KnowledgeEntry(
            key="test:crud:create",
            value="test value",
            tags="test",
            level=0,
            level_name="individual",
        )
        entry_id = store.store(entry)
        assert entry_id
        result = store.get_by_key_and_level("test:crud:create", 0)
        assert result is not None
        assert result.value == "test value"

    def test_update_level_zero(self):
        store = get_dashboard_store()
        entry = KnowledgeEntry(
            key="test:crud:update",
            value="original",
            level=0,
        )
        store.store(entry)
        store.update(
            "test:crud:update",
            "updated",
            reason="test",
            actor="dashboard",
            level=0,
        )
        result = store.get_by_key_and_level("test:crud:update", 0)
        assert result.value == "updated"

    def test_delete_level_zero(self):
        store = get_dashboard_store()
        entry = KnowledgeEntry(
            key="test:crud:delete",
            value="to delete",
            level=0,
        )
        store.store(entry)
        store.delete("test:crud:delete", reason="test", actor="dashboard", level=0)
        result = store.get_by_key_and_level("test:crud:delete", 0)
        assert result is None

    def test_duplicate_key_detection(self):
        store = get_dashboard_store()
        entry = KnowledgeEntry(
            key="test:crud:dup",
            value="first",
            level=0,
        )
        store.store(entry)
        existing = store.get_by_key_and_level("test:crud:dup", 0)
        assert existing is not None

    def test_delete_shared_entry_rejected(self):
        store = get_dashboard_store()
        entry = KnowledgeEntry(
            key="test:crud:shared",
            value="shared value",
            level=1,
            level_name="team",
        )
        store.store(entry)
        with pytest.raises(KeyError):
            store.delete("test:crud:shared", reason="test", actor="dashboard", level=0)
        result = store.get_by_key_and_level("test:crud:shared", 1)
        assert result is not None

    def test_delete_records_history(self):
        store = get_dashboard_store()
        entry = KnowledgeEntry(
            key="test:crud:delhist",
            value="will delete",
            level=0,
        )
        entry_id = store.store(entry)
        store.delete("test:crud:delhist", reason="cleanup", actor="dashboard", level=0)
        history = store.get_history(entry_id)
        actions = [h.action for h in history]
        assert "deleted" in actions
        assert any(h.reason == "cleanup" for h in history)


class TestConflictResolution:
    def _create_conflict_pair(self, store):
        e1 = KnowledgeEntry(
            key="test:conflict:item",
            value="value A",
            level=0,
            level_name="individual",
        )
        e2 = KnowledgeEntry(
            key="test:conflict:item",
            value="value B",
            level=1,
            level_name="team",
            repo_url="https://github.com/org/repo",
            repo_branch="main",
        )
        id1 = store.store(e1)
        id2 = store.store(e2)
        store.apply_conflict(id1, id2)
        store.commit()
        return id1, id2

    def test_apply_conflict_sets_status(self):
        store = get_dashboard_store()
        id1, id2 = self._create_conflict_pair(store)

        winner = store.get_by_id(id1)
        loser = store.get_by_id(id2)
        assert winner.conflict_status == "active"
        assert loser.conflict_status == "overridden"

    def test_clear_conflict(self):
        store = get_dashboard_store()
        id1, id2 = self._create_conflict_pair(store)

        store.clear_conflict(id1)
        store.commit()

        e2 = store.get_by_id(id2)
        assert e2.conflict_with is None
        assert e2.conflict_status is None

    def test_list_conflicts(self):
        store = get_dashboard_store()
        self._create_conflict_pair(store)

        conflicts = store.list_conflicts()
        assert len(conflicts) >= 2

    def test_merge_updates_value(self):
        store = get_dashboard_store()
        id1, id2 = self._create_conflict_pair(store)

        store.update(
            "test:conflict:item",
            "merged value",
            reason="merged via dashboard",
            actor="dashboard",
            level=0,
        )
        store.apply_conflict(id1, id2)
        store.commit()

        winner = store.get_by_id(id1)
        assert winner.value == "merged value"
        assert winner.conflict_status == "active"


class TestEntryHistory:
    def test_history_recorded(self):
        store = get_dashboard_store()
        entry = KnowledgeEntry(
            key="test:history:item",
            value="initial",
            level=0,
        )
        entry_id = store.store(entry)
        store.update(
            "test:history:item",
            "updated",
            reason="testing history",
            actor="dashboard",
            level=0,
        )

        history = store.get_history(entry_id)
        assert len(history) >= 2
        actions = [h.action for h in history]
        assert "created" in actions
        assert "updated" in actions
