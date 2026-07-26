from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from lore.ingest.base import LoreIngester
from lore.store.base import KnowledgeEntry
from lore.store.sqlite import SQLiteStore, create_schema


def _make_store():
    return SQLiteStore(create_schema(":memory:"))


class _SimpleIngester(LoreIngester):
    name = "_test_simple"
    triggers = frozenset({"manual"})

    def __init__(self, store, project_dir, entries=None):
        super().__init__(store, project_dir)
        self._entries = entries or []

    def detect(self, project_dir: Path) -> bool:
        return True

    def extract_delta(self, since: datetime | None = None) -> list[KnowledgeEntry]:
        return list(self._entries)


def _mock_cfg(provider="none", threshold=0.20):
    cfg = MagicMock()
    cfg.search.embedding_provider = provider
    cfg.search.dedup_threshold = threshold
    return cfg


def test_dedup_no_embedding_passthrough(tmp_path):
    store = _make_store()
    entries = [KnowledgeEntry(key="a", value="hello", level=0)]
    ing = _SimpleIngester(store, tmp_path, entries)

    with patch("lore.config.manager.get_global_config", return_value=_mock_cfg("none")):
        result = ing._dedup(entries)
        assert len(result) == 1


def test_dedup_removes_near_duplicates(tmp_path):
    store = _make_store()
    existing = KnowledgeEntry(key="existing:entry", value="hello world", level=0)
    store.store(existing)
    store.commit()

    new_entry = KnowledgeEntry(key="new:entry", value="hello world again", level=0)
    ing = _SimpleIngester(store, tmp_path, [new_entry])

    mock_provider = MagicMock()
    mock_provider.embed.return_value = [0.1] * 10

    with (
        patch(
            "lore.config.manager.get_global_config",
            return_value=_mock_cfg("ollama"),
        ),
        patch("lore.embedding.get_embedding_provider", return_value=mock_provider),
        patch.object(store, "query_vector", return_value=[(existing, 0.05)]),
    ):
        result = ing._dedup([new_entry])
        assert len(result) == 0


def test_dedup_keeps_distant_entries(tmp_path):
    store = _make_store()
    new_entry = KnowledgeEntry(key="new:entry", value="totally different", level=0)
    ing = _SimpleIngester(store, tmp_path, [new_entry])

    mock_provider = MagicMock()
    mock_provider.embed.return_value = [0.1] * 10

    with (
        patch(
            "lore.config.manager.get_global_config",
            return_value=_mock_cfg("ollama"),
        ),
        patch("lore.embedding.get_embedding_provider", return_value=mock_provider),
        patch.object(store, "query_vector", return_value=[]),
    ):
        result = ing._dedup([new_entry])
        assert len(result) == 1


def test_dedup_sets_embedding_blob(tmp_path):
    store = _make_store()
    new_entry = KnowledgeEntry(key="new:entry", value="test blob", level=0)
    ing = _SimpleIngester(store, tmp_path, [new_entry])

    mock_provider = MagicMock()
    mock_provider.embed.return_value = [0.1, 0.2, 0.3]

    with (
        patch(
            "lore.config.manager.get_global_config",
            return_value=_mock_cfg("ollama"),
        ),
        patch("lore.embedding.get_embedding_provider", return_value=mock_provider),
        patch.object(store, "query_vector", return_value=[]),
    ):
        result = ing._dedup([new_entry])
        assert len(result) == 1
        assert result[0].embedding is not None


def test_dedup_embedding_failure_passthrough(tmp_path):
    store = _make_store()
    new_entry = KnowledgeEntry(key="new:entry", value="test", level=0)
    ing = _SimpleIngester(store, tmp_path, [new_entry])

    mock_provider = MagicMock()
    mock_provider.embed.side_effect = Exception("Ollama down")

    with (
        patch(
            "lore.config.manager.get_global_config",
            return_value=_mock_cfg("ollama"),
        ),
        patch("lore.embedding.get_embedding_provider", return_value=mock_provider),
    ):
        result = ing._dedup([new_entry])
        assert len(result) == 1


def test_dedup_empty_entries(tmp_path):
    store = _make_store()
    ing = _SimpleIngester(store, tmp_path)
    result = ing._dedup([])
    assert result == []


def test_dedup_respects_level(tmp_path):
    store = _make_store()
    existing = KnowledgeEntry(key="existing:entry", value="hello", level=1)
    store.store(existing)

    new_entry = KnowledgeEntry(key="new:entry", value="hello", level=0)
    ing = _SimpleIngester(store, tmp_path, [new_entry])

    mock_provider = MagicMock()
    mock_provider.embed.return_value = [0.1] * 10

    with (
        patch(
            "lore.config.manager.get_global_config",
            return_value=_mock_cfg("ollama"),
        ),
        patch("lore.embedding.get_embedding_provider", return_value=mock_provider),
        patch.object(store, "query_vector", return_value=[(existing, 0.05)]),
    ):
        result = ing._dedup([new_entry])
        assert len(result) == 1


def test_run_orchestrates_full_pipeline(tmp_path):
    store = _make_store()
    entries = [KnowledgeEntry(key="run:test", value="pipeline", level=0)]
    ing = _SimpleIngester(store, tmp_path, entries)

    result = ing.run()
    assert len(result) == 1
    stored = store.get("run:test")
    assert stored is not None
    assert stored.value == "pipeline"
