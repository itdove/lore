from __future__ import annotations

from lore.llm.base import LLMProvider
from lore.llm.none import NoneProvider
from lore.store.base import KnowledgeEntry


def _make_entry(**kwargs):
    defaults = {"key": "test:domain:slug", "value": "test value", "level": 0}
    defaults.update(kwargs)
    return KnowledgeEntry(**defaults)


# =====================================================================
# AC2: NoneProvider returns raw results (no LLM dep)
# =====================================================================


def test_none_provider_is_llm_provider():
    assert isinstance(NoneProvider(), LLMProvider)


def test_synthesize_formats_candidates():
    provider = NoneProvider()
    entries = [
        _make_entry(key="bug:api:timeout", value="increase timeout to 30s"),
        _make_entry(key="pattern:api:retry", value="use exponential backoff"),
    ]
    result = provider.synthesize("api", entries)
    assert "[bug:api:timeout]" in result
    assert "increase timeout to 30s" in result
    assert "[pattern:api:retry]" in result
    assert "use exponential backoff" in result


def test_synthesize_empty_returns_message():
    provider = NoneProvider()
    result = provider.synthesize("anything", [])
    assert "no relevant knowledge" in result.lower()


def test_extract_knowledge_returns_empty():
    provider = NoneProvider()
    result = provider.extract_knowledge("some transcript", [])
    assert result == []


def test_extract_knowledge_with_existing_returns_empty():
    provider = NoneProvider()
    existing = [_make_entry(key="k1", value="v1")]
    result = provider.extract_knowledge("transcript", existing)
    assert result == []
