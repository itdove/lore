from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from urllib.parse import urlparse

from lore.embedding.base import EmbeddingProvider

log = logging.getLogger("lore.embedding")

_MODEL_DIMS: dict[str, int] = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,
    "snowflake-arctic-embed": 1024,
    "bge-large": 1024,
    "bge-m3": 1024,
}


class OllamaProvider(EmbeddingProvider):
    def __init__(
        self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434"
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._dims: int | None = _MODEL_DIMS.get(model)

    def _request(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self._model, "input": texts}).encode()
        req = urllib.request.Request(
            f"{self._base_url}/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read(50 * 1024 * 1024)
                data = json.loads(raw)
                embeddings = data.get("embeddings", [])
                if embeddings and self._dims is None:
                    self._dims = len(embeddings[0])
                return embeddings
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            log.warning("Ollama embed request failed: %s", exc)
            return []

    def embed(self, text: str) -> list[float]:
        results = self._request([text])
        return results[0] if results else []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._request(texts)

    @property
    def dimensions(self) -> int:
        if self._dims is not None:
            return self._dims
        self.embed("dimension probe")
        return self._dims or 0
