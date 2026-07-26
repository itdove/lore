from __future__ import annotations

import json

from lore.ingest.base import LoreIngester
from lore.ingest.doc import DocIngester, ingest_file
from lore.llm.base import DocChunkExtraction, LLMProvider
from lore.store.base import KnowledgeEntry
from lore.store.sqlite import SQLiteStore, create_schema


class _MockDocProvider(LLMProvider):
    def __init__(self, extractions=None):
        self._extractions = extractions or []

    def synthesize(self, topic, candidates):
        return ""

    def extract_knowledge(self, transcript, existing, project_config=None):
        return []

    def extract_from_chunk(self, chunk_text, heading, source_file):
        return list(self._extractions)


def _make_store():
    conn = create_schema(":memory:")
    return SQLiteStore(conn)


def _write_md(tmp_path, content="# Title\n" + "word " * 100):
    p = tmp_path / "test.md"
    p.write_text(content)
    return p


def test_doc_ingester_is_lore_ingester(tmp_path):
    p = _write_md(tmp_path)
    ingester = DocIngester(p, _MockDocProvider(), _make_store())
    assert isinstance(ingester, LoreIngester)


def test_doc_ingester_detect_existing_file(tmp_path):
    p = _write_md(tmp_path)
    ingester = DocIngester(p, _MockDocProvider(), _make_store())
    assert ingester.detect(tmp_path) is True


def test_doc_ingester_detect_missing_file(tmp_path):
    p = tmp_path / "missing.md"
    ingester = DocIngester(p, _MockDocProvider(), _make_store())
    assert ingester.detect(tmp_path) is False


def test_doc_ingester_detect_unsupported_format(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b,c")
    ingester = DocIngester(p, _MockDocProvider(), _make_store())
    assert ingester.detect(tmp_path) is False


def test_extract_delta_returns_entries(tmp_path):
    p = _write_md(tmp_path)
    extractions = [
        DocChunkExtraction(
            key="guide:test:intro",
            summary="Test introduction content.",
            tags=["test", "guide"],
            content_type="general",
        )
    ]
    provider = _MockDocProvider(extractions)
    store = _make_store()
    ingester = DocIngester(p, provider, store, level=0)

    entries = ingester.extract_delta()
    assert len(entries) == 1
    assert entries[0].key == "guide:test:intro"
    assert entries[0].value == "Test introduction content."
    assert entries[0].level == 0


def test_extract_delta_sets_provenance(tmp_path):
    p = _write_md(tmp_path)
    extractions = [
        DocChunkExtraction(key="guide:test:prov", summary="Provenance test.")
    ]
    provider = _MockDocProvider(extractions)
    ingester = DocIngester(p, provider, _make_store())

    entries = ingester.extract_delta()
    assert entries[0].ingested_from == "doc-ingester"
    prov = json.loads(entries[0].provenance)
    assert prov["source_file"] == str(p)
    assert "chunk_index" in prov
    assert "heading" in prov


def test_extract_delta_sets_level(tmp_path):
    p = _write_md(tmp_path)
    extractions = [DocChunkExtraction(key="guide:test:level", summary="Level test.")]
    provider = _MockDocProvider(extractions)
    ingester = DocIngester(p, provider, _make_store(), level=2, level_name="team")

    entries = ingester.extract_delta()
    assert entries[0].level == 2
    assert entries[0].level_name == "team"


def test_extract_delta_sets_tags(tmp_path):
    p = _write_md(tmp_path)
    extractions = [
        DocChunkExtraction(
            key="guide:test:tags", summary="Tags test.", tags=["deploy", "k8s"]
        )
    ]
    provider = _MockDocProvider(extractions)
    ingester = DocIngester(p, provider, _make_store())

    entries = ingester.extract_delta()
    assert entries[0].tags == "deploy,k8s"


def test_extract_delta_skips_invalid_keys(tmp_path):
    p = _write_md(tmp_path)
    extractions = [
        DocChunkExtraction(key="valid:key", summary="Good."),
        DocChunkExtraction(key="invalid key with spaces", summary="Bad."),
    ]
    provider = _MockDocProvider(extractions)
    ingester = DocIngester(p, provider, _make_store())

    entries = ingester.extract_delta()
    assert len(entries) == 1
    assert entries[0].key == "valid:key"


def test_transform_identity(tmp_path):
    p = _write_md(tmp_path)
    ingester = DocIngester(p, _MockDocProvider(), _make_store())
    entries = [KnowledgeEntry(key="a", value="b", level=0)]
    assert ingester.transform(entries) == entries


def test_load_stores_entries(tmp_path):
    p = _write_md(tmp_path)
    store = _make_store()
    ingester = DocIngester(p, _MockDocProvider(), store)
    entries = [
        KnowledgeEntry(key="test:load", value="Stored value.", level=0),
    ]
    ingester.load(entries)
    stored = store.get("test:load")
    assert stored is not None
    assert stored.value == "Stored value."


def test_ingest_file_end_to_end(tmp_path):
    p = _write_md(tmp_path)
    extractions = [DocChunkExtraction(key="guide:e2e:test", summary="End to end.")]
    provider = _MockDocProvider(extractions)
    store = _make_store()

    entries = ingest_file(p, provider, store, level=0)
    assert len(entries) == 1
    stored = store.get("guide:e2e:test")
    assert stored is not None


def test_ingest_file_no_frontmatter(tmp_path):
    p = tmp_path / "nofm.md"
    p.write_text("# Header\n" + "Content here. " * 50)
    extractions = [DocChunkExtraction(key="guide:nofm:test", summary="No frontmatter.")]
    provider = _MockDocProvider(extractions)
    store = _make_store()

    entries = ingest_file(p, provider, store)
    assert len(entries) == 1


def test_ingest_file_empty_document(tmp_path):
    p = tmp_path / "empty.md"
    p.write_text("")
    provider = _MockDocProvider([DocChunkExtraction(key="a:b", summary="x")])
    store = _make_store()

    entries = ingest_file(p, provider, store)
    assert entries == []


def test_ingest_file_missing_file(tmp_path):
    p = tmp_path / "missing.md"
    provider = _MockDocProvider()
    store = _make_store()

    entries = ingest_file(p, provider, store)
    assert entries == []
