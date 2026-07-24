from __future__ import annotations

from lore.embedding.base import EmbeddingProvider


class NoneProvider(EmbeddingProvider):
    def embed(self, text: str) -> list[float]:
        return []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]

    @property
    def dimensions(self) -> int:
        return 0
