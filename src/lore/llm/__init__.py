from __future__ import annotations

from lore.llm.base import KnowledgeCandidate, LLMProvider
from lore.llm.none import NoneProvider
from lore.llm.ollama import OllamaProvider

__all__ = [
    "KnowledgeCandidate",
    "LLMProvider",
    "NoneProvider",
    "OllamaProvider",
    "get_llm_provider",
]


def get_llm_provider() -> LLMProvider:
    from lore.config.manager import get_global_config

    cfg = get_global_config()
    provider = cfg.llm.provider
    if not provider or provider == "none":
        return NoneProvider()
    if provider == "ollama":
        model = cfg.llm.model or "phi4-mini"
        base_url = cfg.llm.base_url or "http://localhost:11434"
        return OllamaProvider(model=model, base_url=base_url)
    raise ValueError(f"Unknown LLM provider: {provider!r}")
