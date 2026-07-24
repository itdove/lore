from __future__ import annotations

from lore.embedding.base import EmbeddingProvider, blob_to_embed, embed_to_blob
from lore.embedding.none import NoneProvider
from lore.embedding.ollama import OllamaProvider

__all__ = [
    "EmbeddingProvider",
    "NoneProvider",
    "OllamaProvider",
    "blob_to_embed",
    "embed_to_blob",
    "get_embedding_provider",
]


def get_embedding_provider() -> EmbeddingProvider:
    from lore.config.manager import get_global_config

    cfg = get_global_config()
    provider = cfg.search.embedding_provider
    if not provider or provider == "none":
        return NoneProvider()
    if provider == "ollama":
        model = cfg.search.embedding_model or "nomic-embed-text"
        base_url = cfg.search.embedding_base_url or "http://localhost:11434"
        return OllamaProvider(model=model, base_url=base_url)
    raise ValueError(f"Unknown embedding provider: {provider!r}")
