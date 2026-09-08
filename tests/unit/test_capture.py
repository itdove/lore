from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from lore.capture import CaptureResult, capture_knowledge
from lore.llm.base import KnowledgeCandidate, LLMProvider
from lore.store.base import KnowledgeEntry
from lore.store.sqlite import SQLiteStore, create_schema


def _make_entry(**kwargs):
    defaults = {"key": "test:domain:slug", "value": "test value", "level": 0}
    defaults.update(kwargs)
    return KnowledgeEntry(**defaults)


class _MockProvider(LLMProvider):
    def __init__(self, candidates: list[KnowledgeCandidate] | None = None):
        self._candidates = candidates or []

    def synthesize(self, topic, candidates):
        return "mock synthesis"

    def extract_knowledge(self, transcript, existing, project_config=None):
        return self._candidates

    def extract_from_chunk(self, chunk_text, heading, source_file):
        return []


@pytest.fixture
def store():
    conn = create_schema(":memory:")
    return SQLiteStore(conn)


# =====================================================================
# AC4: Capture extracts structured candidates from transcript
# =====================================================================


def test_capture_returns_capture_result(store):
    provider = _MockProvider()
    result = capture_knowledge("transcript", store, provider)
    assert isinstance(result, CaptureResult)


def test_capture_passes_existing_to_provider(store, monkeypatch):
    store.store(_make_entry(key="k1", value="v1"))
    received = {}

    class _SpyProvider(LLMProvider):
        def synthesize(self, topic, candidates):
            return ""

        def extract_knowledge(self, transcript, existing, project_config=None):
            received["existing"] = existing
            return []

        def extract_from_chunk(self, chunk_text, heading, source_file):
            return []

    capture_knowledge("transcript", store, _SpyProvider())
    assert len(received["existing"]) == 1
    assert received["existing"][0].key == "k1"


def test_capture_passes_relevant_existing_entries_to_provider(store, monkeypatch):
    relevant = _make_entry(key="relevant:api:timeout", value="Use a 30 second timeout.")
    unrelated = _make_entry(key="unrelated:ui:theme", value="Use the dark theme.")
    store.store(relevant)
    store.store(unrelated)
    received = {}

    class _SpyProvider(LLMProvider):
        def synthesize(self, topic, candidates):
            return ""

        def extract_knowledge(self, transcript, existing, project_config=None):
            received["existing"] = existing
            return []

        def extract_from_chunk(self, chunk_text, heading, source_file):
            return []

    embedding_provider = mock.Mock()
    embedding_provider.embed.return_value = [0.1, 0.2]
    config = SimpleNamespace(
        search=SimpleNamespace(
            embedding_provider="ollama",
            dedup_threshold=0.2,
        )
    )
    query_vector = mock.Mock(return_value=[(relevant, 0.05)])
    monkeypatch.setattr("lore.config.manager.get_global_config", lambda: config)
    monkeypatch.setattr(
        "lore.embedding.get_embedding_provider",
        lambda: embedding_provider,
    )
    monkeypatch.setattr(store, "query_vector", query_vector)

    capture_knowledge("transcript about timeouts", store, _SpyProvider())

    assert [entry.key for entry in received["existing"]] == [relevant.key]
    assert received["existing"][0].value == relevant.value
    embedding_provider.embed.assert_called_once_with("transcript about timeouts")
    query_vector.assert_called_once_with(
        [0.1, 0.2],
        limit=20,
        filter_levels=None,
    )


def test_capture_falls_back_to_keys_only_when_embedding_unavailable(store, monkeypatch):
    first = _make_entry(key="first:key", value="first value")
    second = _make_entry(key="second:key", value="second value")
    store.store(first)
    store.store(second)
    received = {}

    class _SpyProvider(LLMProvider):
        def synthesize(self, topic, candidates):
            return ""

        def extract_knowledge(self, transcript, existing, project_config=None):
            received["existing"] = existing
            return []

        def extract_from_chunk(self, chunk_text, heading, source_file):
            return []

    embedding_provider = mock.Mock()
    embedding_provider.embed.return_value = []
    config = SimpleNamespace(
        search=SimpleNamespace(
            embedding_provider="ollama",
            dedup_threshold=0.2,
        )
    )
    query_vector = mock.Mock()
    monkeypatch.setattr("lore.config.manager.get_global_config", lambda: config)
    monkeypatch.setattr(
        "lore.embedding.get_embedding_provider",
        lambda: embedding_provider,
    )
    monkeypatch.setattr(store, "query_vector", query_vector)

    capture_knowledge("transcript", store, _SpyProvider())

    assert [(entry.key, entry.value) for entry in received["existing"]] == [
        (first.key, ""),
        (second.key, ""),
    ]
    query_vector.assert_not_called()


def test_capture_exact_duplicate_check_uses_all_existing_entries(store, monkeypatch):
    exact_match = _make_entry(key="existing:exact", value="same value")
    relevant = _make_entry(key="relevant:other", value="other value")
    store.store(exact_match)
    store.store(relevant)

    config = SimpleNamespace(
        search=SimpleNamespace(
            embedding_provider="ollama",
            dedup_threshold=0.2,
        )
    )
    embedding_provider = mock.Mock()
    embedding_provider.embed.return_value = [0.1, 0.2]
    monkeypatch.setattr("lore.config.manager.get_global_config", lambda: config)
    monkeypatch.setattr(
        "lore.embedding.get_embedding_provider",
        lambda: embedding_provider,
    )
    monkeypatch.setattr(
        store,
        "query_vector",
        mock.Mock(return_value=[(relevant, 0.05)]),
    )

    result = capture_knowledge(
        "transcript",
        store,
        _MockProvider(
            [KnowledgeCandidate(key=exact_match.key, value=exact_match.value)]
        ),
    )

    assert result.duplicates == [result.candidates[0]]
    assert result.new == []


# =====================================================================
# AC5: Candidates include suggested_level
# =====================================================================


def test_candidate_preserves_suggested_level(store):
    candidates = [
        KnowledgeCandidate(key="new:thing:one", value="v", suggested_level="team")
    ]
    provider = _MockProvider(candidates)
    result = capture_knowledge("transcript", store, provider)
    assert result.new[0].suggested_level == "team"


# =====================================================================
# AC6: Dedup against existing entries works
# =====================================================================


def test_new_candidate_classified(store):
    candidates = [KnowledgeCandidate(key="new:key:one", value="new value")]
    provider = _MockProvider(candidates)
    result = capture_knowledge("transcript", store, provider)
    assert len(result.new) == 1
    assert len(result.duplicates) == 0
    assert len(result.updates) == 0


def test_duplicate_candidate_classified(store):
    store.store(_make_entry(key="dup:key:one", value="same value"))
    candidates = [KnowledgeCandidate(key="dup:key:one", value="same value")]
    provider = _MockProvider(candidates)
    result = capture_knowledge("transcript", store, provider)
    assert len(result.duplicates) == 1
    assert len(result.new) == 0


def test_update_candidate_classified(store):
    store.store(_make_entry(key="upd:key:one", value="old value"))
    candidates = [KnowledgeCandidate(key="upd:key:one", value="new value")]
    provider = _MockProvider(candidates)
    result = capture_knowledge("transcript", store, provider)
    assert len(result.updates) == 1
    assert len(result.duplicates) == 0


def test_mixed_classification(store):
    store.store(_make_entry(key="existing:dup:one", value="same"))
    store.store(_make_entry(key="existing:upd:one", value="old"))
    candidates = [
        KnowledgeCandidate(key="brand:new:one", value="new"),
        KnowledgeCandidate(key="existing:dup:one", value="same"),
        KnowledgeCandidate(key="existing:upd:one", value="changed"),
    ]
    provider = _MockProvider(candidates)
    result = capture_knowledge("transcript", store, provider)
    assert len(result.candidates) == 3
    assert len(result.new) == 1
    assert len(result.duplicates) == 1
    assert len(result.updates) == 1


# =====================================================================
# AC7: Stale entry detection returns negation candidates
# =====================================================================


def test_negation_candidate_classified(store):
    store.store(_make_entry(key="old:pattern:one", value="old way"))
    candidates = [
        KnowledgeCandidate(
            key="new:pattern:one",
            value="new way",
            negate_key="old:pattern:one",
            negate_reason="old approach deprecated",
        )
    ]
    provider = _MockProvider(candidates)
    result = capture_knowledge("transcript", store, provider)
    assert len(result.negations) == 1
    assert result.negations[0].negate_key == "old:pattern:one"
    assert result.negations[0].negate_reason == "old approach deprecated"


def test_negation_candidate_also_classified_as_new(store):
    candidates = [
        KnowledgeCandidate(
            key="new:thing:one",
            value="replacement",
            negate_key="old:thing:one",
            negate_reason="stale",
        )
    ]
    provider = _MockProvider(candidates)
    result = capture_knowledge("transcript", store, provider)
    assert len(result.negations) == 1
    assert len(result.new) == 1


def test_empty_candidates(store):
    provider = _MockProvider([])
    result = capture_knowledge("transcript", store, provider)
    assert result.candidates == []
    assert result.new == []
    assert result.updates == []
    assert result.duplicates == []
    assert result.negations == []
