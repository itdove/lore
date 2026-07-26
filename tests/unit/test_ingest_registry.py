from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lore.ingest.base import LoreIngester
from lore.ingest.registry import (
    _REGISTRY,
    detect_ingesters,
    get_ingester,
    list_ingesters,
    register,
)
from lore.store.base import KnowledgeEntry
from lore.store.sqlite import SQLiteStore, create_schema


def _make_store():
    return SQLiteStore(create_schema(":memory:"))


class _DummyIngester(LoreIngester):
    name = "_test_dummy"
    triggers = frozenset({"manual"})
    auto_detect = True

    def detect(self, project_dir: Path) -> bool:
        return (project_dir / "dummy.txt").exists()

    def extract_delta(self, since: datetime | None = None) -> list[KnowledgeEntry]:
        return [KnowledgeEntry(key="dummy:entry", value="dummy", level=0)]


class _NoAutoIngester(LoreIngester):
    name = "_test_noauto"
    triggers = frozenset({"manual"})
    auto_detect = False

    def detect(self, project_dir: Path) -> bool:
        return True

    def extract_delta(self, since: datetime | None = None) -> list[KnowledgeEntry]:
        return []


def _with_clean_registry(fn):
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        saved = dict(_REGISTRY)
        try:
            return fn(*a, **kw)
        finally:
            _REGISTRY.clear()
            _REGISTRY.update(saved)

    return wrapper


@_with_clean_registry
def test_register_decorator():
    @register
    class _Reg(LoreIngester):
        name = "_test_reg"
        triggers = frozenset({"manual"})

        def detect(self, project_dir):
            return False

        def extract_delta(self, since=None):
            return []

    assert "_test_reg" in _REGISTRY
    assert _REGISTRY["_test_reg"] is _Reg


@_with_clean_registry
def test_get_ingester_known(tmp_path):
    register(_DummyIngester)
    ing = get_ingester("_test_dummy", _make_store(), tmp_path)
    assert isinstance(ing, _DummyIngester)


@_with_clean_registry
def test_get_ingester_unknown():
    import pytest

    with pytest.raises(ValueError, match="Unknown ingester"):
        get_ingester("nonexistent", _make_store(), Path("/tmp"))


@_with_clean_registry
def test_detect_ingesters_finds_match(tmp_path):
    register(_DummyIngester)
    (tmp_path / "dummy.txt").write_text("x")
    detected = detect_ingesters(tmp_path, _make_store())
    assert any(isinstance(d, _DummyIngester) for d in detected)


@_with_clean_registry
def test_detect_ingesters_no_match(tmp_path):
    register(_DummyIngester)
    detected = detect_ingesters(tmp_path, _make_store())
    assert not any(isinstance(d, _DummyIngester) for d in detected)


@_with_clean_registry
def test_detect_skips_auto_detect_false(tmp_path):
    register(_NoAutoIngester)
    detected = detect_ingesters(tmp_path, _make_store())
    assert not any(isinstance(d, _NoAutoIngester) for d in detected)


@_with_clean_registry
def test_detect_respects_disabled_sources(tmp_path):
    register(_DummyIngester)
    (tmp_path / "dummy.txt").write_text("x")
    detected = detect_ingesters(
        tmp_path, _make_store(), disabled_sources=["_test_dummy"]
    )
    assert not any(isinstance(d, _DummyIngester) for d in detected)


def test_list_ingesters_returns_sorted():
    names = list_ingesters()
    assert names == sorted(names)


def test_builtin_ingesters_registered():
    names = list_ingesters()
    assert "doc" in names
    assert "openwolf" in names
    assert "reasonsforge" in names
