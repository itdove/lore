from __future__ import annotations

import pytest

from lore.config.models import GlobalConfig, LLMConfig
from lore.llm import get_llm_provider
from lore.llm.none import NoneProvider
from lore.llm.ollama import OllamaProvider

# =====================================================================
# AC8: Config selects provider via llm.provider + llm.model
# =====================================================================


def test_returns_none_provider_when_none(monkeypatch):
    cfg = GlobalConfig(llm=LLMConfig(provider="none"))
    monkeypatch.setattr("lore.config.manager.get_global_config", lambda: cfg)
    provider = get_llm_provider()
    assert isinstance(provider, NoneProvider)


def test_returns_none_provider_when_empty(monkeypatch):
    cfg = GlobalConfig(llm=LLMConfig(provider=""))
    monkeypatch.setattr("lore.config.manager.get_global_config", lambda: cfg)
    provider = get_llm_provider()
    assert isinstance(provider, NoneProvider)


def test_returns_ollama_provider(monkeypatch):
    cfg = GlobalConfig(
        llm=LLMConfig(
            provider="ollama",
            model="qwen2.5:3b",
            base_url="http://localhost:11434",
        )
    )
    monkeypatch.setattr("lore.config.manager.get_global_config", lambda: cfg)
    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)
    assert provider._model == "qwen2.5:3b"
    assert provider._base_url == "http://localhost:11434"


def test_ollama_default_model(monkeypatch):
    cfg = GlobalConfig(llm=LLMConfig(provider="ollama"))
    monkeypatch.setattr("lore.config.manager.get_global_config", lambda: cfg)
    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)
    assert provider._model == "phi4-mini"


def test_unknown_provider_raises(monkeypatch):
    cfg = GlobalConfig(llm=LLMConfig(provider="unknown"))
    monkeypatch.setattr("lore.config.manager.get_global_config", lambda: cfg)
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_provider()
