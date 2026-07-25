from __future__ import annotations

import json
import unittest.mock
from unittest import mock

import pytest

from lore.config.models import GlobalConfig, SearchConfig
from lore.embedding import get_embedding_provider
from lore.embedding.base import (
    EmbeddingProvider,
    blob_to_embed,
    cosine_distance,
    embed_to_blob,
)
from lore.embedding.none import NoneProvider
from lore.embedding.ollama import OllamaProvider


def test_embedding_provider_is_abstract():
    with pytest.raises(TypeError):
        EmbeddingProvider()


def test_none_provider_embed():
    p = NoneProvider()
    assert p.embed("hello") == []


def test_none_provider_embed_batch():
    p = NoneProvider()
    assert p.embed_batch(["a", "b", "c"]) == [[], [], []]


def test_none_provider_dimensions():
    p = NoneProvider()
    assert p.dimensions == 0


def _mock_ollama_response(embeddings: list[list[float]]) -> mock.MagicMock:
    body = json.dumps({"model": "nomic-embed-text", "embeddings": embeddings}).encode()
    resp = mock.MagicMock()
    resp.read.return_value = body
    resp.__enter__ = mock.Mock(return_value=resp)
    resp.__exit__ = mock.Mock(return_value=False)
    return resp


def test_ollama_embed():
    p = OllamaProvider(model="nomic-embed-text")
    resp = _mock_ollama_response([[0.1, 0.2, 0.3]])
    with mock.patch("urllib.request.urlopen", return_value=resp):
        result = p.embed("hello")
    assert result == [0.1, 0.2, 0.3]


def test_ollama_embed_batch():
    p = OllamaProvider(model="nomic-embed-text")
    resp = _mock_ollama_response([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    with mock.patch("urllib.request.urlopen", return_value=resp):
        result = p.embed_batch(["hello", "world"])
    assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


def test_ollama_dimensions_known_model():
    p = OllamaProvider(model="nomic-embed-text")
    assert p.dimensions == 768


def test_ollama_dimensions_unknown_model_probes():
    p = OllamaProvider(model="custom-model")
    resp = _mock_ollama_response([[0.0] * 256])
    with mock.patch("urllib.request.urlopen", return_value=resp):
        assert p.dimensions == 256


def test_ollama_http_failure_returns_empty():
    p = OllamaProvider(model="nomic-embed-text")
    with mock.patch(
        "urllib.request.urlopen",
        side_effect=ConnectionError("refused"),
    ):
        result = p.embed("hello")
    assert result == []


def test_ollama_embed_batch_empty():
    p = OllamaProvider(model="nomic-embed-text")
    assert p.embed_batch([]) == []


def test_embed_to_blob_roundtrip():
    original = [1.0, 2.0, 3.0, -0.5]
    blob = embed_to_blob(original)
    recovered = blob_to_embed(blob)
    assert len(recovered) == len(original)
    for a, b in zip(original, recovered):
        assert abs(a - b) < 1e-6


def test_embed_to_blob_empty():
    assert embed_to_blob([]) == b""
    assert blob_to_embed(b"") == []


def test_cosine_distance_identical():
    v = [1.0, 2.0, 3.0]
    assert abs(cosine_distance(v, v)) < 1e-9


def test_cosine_distance_orthogonal():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(cosine_distance(a, b) - 1.0) < 1e-9


def test_cosine_distance_opposite():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert abs(cosine_distance(a, b) - 2.0) < 1e-9


def test_factory_none():
    cfg = GlobalConfig(search=SearchConfig(embedding_provider="none"))
    with unittest.mock.patch("lore.config.manager.get_global_config", return_value=cfg):
        p = get_embedding_provider()
        assert isinstance(p, NoneProvider)


def test_factory_ollama():
    cfg = GlobalConfig(
        search=SearchConfig(
            embedding_provider="ollama",
            embedding_model="nomic-embed-text",
            embedding_base_url="http://localhost:11434",
        )
    )
    with unittest.mock.patch("lore.config.manager.get_global_config", return_value=cfg):
        p = get_embedding_provider()
        assert isinstance(p, OllamaProvider)


def test_factory_unknown_raises():
    cfg = GlobalConfig(search=SearchConfig(embedding_provider="openai"))
    with unittest.mock.patch("lore.config.manager.get_global_config", return_value=cfg):
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            get_embedding_provider()


def test_search_config_min_similarity_default():
    sc = SearchConfig()
    assert sc.min_similarity == 0.3


def test_search_config_min_similarity_custom():
    sc = SearchConfig(min_similarity=0.5)
    assert sc.min_similarity == 0.5


def test_search_config_min_similarity_invalid():
    with pytest.raises(ValueError, match="min_similarity must be in"):
        SearchConfig(min_similarity=1.5)
    with pytest.raises(ValueError, match="min_similarity must be in"):
        SearchConfig(min_similarity=-0.1)
