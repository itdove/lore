from __future__ import annotations

import json
import urllib.error

from lore.llm.base import LLMProvider
from lore.llm.ollama import OllamaProvider, _parse_candidates
from lore.store.base import KnowledgeEntry


def _make_entry(**kwargs):
    defaults = {"key": "test:domain:slug", "value": "test value", "level": 0}
    defaults.update(kwargs)
    return KnowledgeEntry(**defaults)


def _mock_urlopen(response_data):
    class MockResponse:
        def __init__(self):
            self._data = json.dumps(response_data).encode()

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    return lambda *a, **kw: MockResponse()


# =====================================================================
# AC3: OllamaProvider connects to local Ollama and synthesizes
# =====================================================================


def test_ollama_provider_is_llm_provider():
    p = OllamaProvider(model="phi4-mini")
    assert isinstance(p, LLMProvider)


def test_constructor_stores_fields():
    p = OllamaProvider(model="phi4-mini", base_url="http://custom:9999")
    assert p._model == "phi4-mini"
    assert p._base_url == "http://custom:9999"


def test_constructor_strips_trailing_slash():
    p = OllamaProvider(model="m", base_url="http://host:1234/")
    assert p._base_url == "http://host:1234"


def test_model_tier_small_models():
    for model in ("phi4-mini", "qwen2.5:3b", "gemma:2b", "phi:latest", "model:1b"):
        p = OllamaProvider(model=model)
        assert p._model_tier() == "small", f"expected small for {model}"


def test_model_tier_medium_models():
    for model in ("llama3:70b", "mixtral", "codestral"):
        p = OllamaProvider(model=model)
        assert p._model_tier() == "medium", f"expected medium for {model}"


def test_generate_sends_request(monkeypatch):
    p = OllamaProvider(model="phi4-mini")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _mock_urlopen({"response": "synthesized answer"}),
    )
    result = p._generate("test prompt")
    assert result == "synthesized answer"


def test_generate_handles_url_error(monkeypatch):
    p = OllamaProvider(model="phi4-mini")

    def fail(*a, **kw):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    result = p._generate("test prompt")
    assert result == ""


def test_generate_handles_json_error(monkeypatch):
    class BadResponse:
        def read(self):
            return b"not json"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: BadResponse())
    p = OllamaProvider(model="phi4-mini")
    result = p._generate("test")
    assert result == ""


def test_synthesize_returns_response(monkeypatch):
    p = OllamaProvider(model="phi4-mini")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _mock_urlopen({"response": "The timeout should be 30s."}),
    )
    entries = [_make_entry(key="bug:api:timeout", value="increase to 30s")]
    result = p.synthesize("api timeout", entries)
    assert result == "The timeout should be 30s."


def test_synthesize_empty_candidates():
    p = OllamaProvider(model="phi4-mini")
    result = p.synthesize("anything", [])
    assert "no relevant knowledge" in result.lower()


def test_synthesize_fallback_on_empty_response(monkeypatch):
    p = OllamaProvider(model="phi4-mini")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _mock_urlopen({"response": ""}),
    )
    entries = [_make_entry()]
    result = p.synthesize("topic", entries)
    assert "no relevant knowledge" in result.lower()


def test_extract_knowledge_parses_json(monkeypatch):
    candidates_json = [
        {
            "key": "bug:api:timeout",
            "value": "root cause: missing timeout config",
            "tags": ["api"],
            "suggested_level": "team",
        }
    ]
    p = OllamaProvider(model="phi4-mini")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _mock_urlopen({"response": json.dumps(candidates_json)}),
    )
    result = p.extract_knowledge("session transcript", [])
    assert len(result) == 1
    assert result[0].key == "bug:api:timeout"
    assert result[0].suggested_level == "team"


def test_extract_knowledge_empty_response(monkeypatch):
    p = OllamaProvider(model="phi4-mini")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _mock_urlopen({"response": ""}),
    )
    result = p.extract_knowledge("transcript", [])
    assert result == []


def test_extract_knowledge_malformed_json(monkeypatch):
    p = OllamaProvider(model="phi4-mini")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _mock_urlopen({"response": "not valid json at all"}),
    )
    result = p.extract_knowledge("transcript", [])
    assert result == []


# =====================================================================
# _parse_candidates unit tests
# =====================================================================


def test_parse_candidates_basic():
    raw = json.dumps([{"key": "k", "value": "v"}])
    result = _parse_candidates(raw)
    assert len(result) == 1
    assert result[0].key == "k"
    assert result[0].value == "v"


def test_parse_candidates_with_code_fence():
    raw = '```json\n[{"key": "k", "value": "v"}]\n```'
    result = _parse_candidates(raw)
    assert len(result) == 1


def test_parse_candidates_with_negation():
    raw = json.dumps(
        [
            {
                "key": "k",
                "value": "v",
                "negate_key": "old:key:name",
                "negate_reason": "outdated",
            }
        ]
    )
    result = _parse_candidates(raw)
    assert result[0].negate_key == "old:key:name"
    assert result[0].negate_reason == "outdated"


def test_parse_candidates_skips_invalid_items():
    raw = json.dumps(
        [
            {"key": "k", "value": "v"},
            {"no_key": True},
            "not a dict",
            {"key": "k2", "value": "v2"},
        ]
    )
    result = _parse_candidates(raw)
    assert len(result) == 2


def test_parse_candidates_no_array():
    result = _parse_candidates("just some text with no json")
    assert result == []


def test_parse_candidates_defaults():
    raw = json.dumps([{"key": "k", "value": "v"}])
    result = _parse_candidates(raw)
    c = result[0]
    assert c.tags == []
    assert c.suggested_level == "individual"
    assert c.negate_key is None
    assert c.negate_reason is None
