from __future__ import annotations

from pathlib import Path

from lore.ingest.doc_repo import DocRepoIngester
from lore.llm.base import DocChunkExtraction, LLMProvider
from lore.sync.parser import ParsedFile


class _MockProvider(LLMProvider):
    def __init__(self, extractions=None):
        self._extractions = extractions or []

    def synthesize(self, topic, candidates):
        return ""

    def extract_knowledge(self, transcript, existing, project_config=None):
        return []

    def extract_from_chunk(self, chunk_text, heading, source_file):
        return list(self._extractions)


def _write_doc(path: Path, content: str = "# Title\n" + "word " * 100):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_scan_files_entire_repo(tmp_path):
    _write_doc(tmp_path / "guide.md")
    _write_doc(tmp_path / "sub" / "ref.md")
    _write_doc(tmp_path / "data.csv", "a,b,c")

    ingester = DocRepoIngester(_MockProvider())
    files = ingester.scan_files(tmp_path)
    names = {f.name for f in files}
    assert "guide.md" in names
    assert "ref.md" in names
    assert "data.csv" not in names


def test_scan_files_doc_paths_filter(tmp_path):
    _write_doc(tmp_path / "docs" / "guide.md")
    _write_doc(tmp_path / "docs" / "ref.md")
    _write_doc(tmp_path / "internal" / "secret.md")

    ingester = DocRepoIngester(_MockProvider(), doc_paths=["docs"])
    files = ingester.scan_files(tmp_path)
    names = {f.name for f in files}
    assert "guide.md" in names
    assert "ref.md" in names
    assert "secret.md" not in names


def test_scan_files_multiple_doc_paths(tmp_path):
    _write_doc(tmp_path / "guides" / "a.md")
    _write_doc(tmp_path / "reference" / "b.md")
    _write_doc(tmp_path / "other" / "c.md")

    ingester = DocRepoIngester(_MockProvider(), doc_paths=["guides", "reference"])
    files = ingester.scan_files(tmp_path)
    names = {f.name for f in files}
    assert names == {"a.md", "b.md"}


def test_scan_files_exclude_paths(tmp_path):
    _write_doc(tmp_path / "docs" / "public.md")
    _write_doc(tmp_path / "docs" / "internal" / "private.md")

    ingester = DocRepoIngester(
        _MockProvider(),
        doc_paths=["docs"],
        exclude_paths=["docs/internal"],
    )
    files = ingester.scan_files(tmp_path)
    names = {f.name for f in files}
    assert "public.md" in names
    assert "private.md" not in names


def test_scan_files_skips_dotdirs(tmp_path):
    _write_doc(tmp_path / ".hidden" / "secret.md")
    _write_doc(tmp_path / "visible.md")

    ingester = DocRepoIngester(_MockProvider())
    files = ingester.scan_files(tmp_path)
    names = {f.name for f in files}
    assert "visible.md" in names
    assert "secret.md" not in names


def test_scan_files_supported_extensions(tmp_path):
    _write_doc(tmp_path / "a.md")
    _write_doc(tmp_path / "b.rst")
    _write_doc(tmp_path / "c.txt")
    _write_doc(tmp_path / "d.adoc")
    _write_doc(tmp_path / "e.py", "print('hi')")

    ingester = DocRepoIngester(_MockProvider())
    files = ingester.scan_files(tmp_path)
    exts = {f.suffix for f in files}
    assert exts == {".md", ".rst", ".txt", ".adoc"}


def test_process_file_returns_parsed_files(tmp_path):
    doc = _write_doc(tmp_path / "guide.md")
    extractions = [
        DocChunkExtraction(
            key="guide:test:intro",
            summary="Test content.",
            tags=["test"],
        )
    ]
    ingester = DocRepoIngester(_MockProvider(extractions))
    result = ingester.process_file(doc, tmp_path)

    assert len(result) == 1
    assert isinstance(result[0], ParsedFile)
    assert result[0].key == "guide:test:intro"
    assert result[0].value == "Test content."
    assert result[0].tags == "test"
    assert result[0].file_path == "guide.md"
    assert result[0].content_hash.startswith("sha256:")
    assert result[0].locked is False


def test_process_file_multiple_extractions(tmp_path):
    doc = _write_doc(tmp_path / "multi.md")
    extractions = [
        DocChunkExtraction(key="guide:a", summary="First."),
        DocChunkExtraction(key="guide:b", summary="Second.", tags=["x", "y"]),
    ]
    ingester = DocRepoIngester(_MockProvider(extractions))
    result = ingester.process_file(doc, tmp_path)

    assert len(result) == 2
    assert result[0].key == "guide:a"
    assert result[1].tags == "x,y"


def test_process_file_skips_invalid_keys(tmp_path):
    doc = _write_doc(tmp_path / "bad.md")
    extractions = [
        DocChunkExtraction(key="valid:key", summary="Good."),
        DocChunkExtraction(key="invalid key spaces", summary="Bad."),
    ]
    ingester = DocRepoIngester(_MockProvider(extractions))
    result = ingester.process_file(doc, tmp_path)

    assert len(result) == 1
    assert result[0].key == "valid:key"


def test_process_file_nested_path(tmp_path):
    doc = _write_doc(tmp_path / "docs" / "sub" / "deep.md")
    extractions = [DocChunkExtraction(key="guide:deep", summary="Deep.")]
    ingester = DocRepoIngester(_MockProvider(extractions))
    result = ingester.process_file(doc, tmp_path)

    assert result[0].file_path == "docs/sub/deep.md"


def test_scan_and_process_end_to_end(tmp_path):
    _write_doc(tmp_path / "docs" / "guide.md")
    _write_doc(tmp_path / "docs" / "ref.md")
    _write_doc(tmp_path / "internal" / "skip.md")

    extractions = [DocChunkExtraction(key="guide:entry", summary="An entry.")]
    ingester = DocRepoIngester(
        _MockProvider(extractions),
        doc_paths=["docs"],
        exclude_paths=["internal"],
    )
    result = ingester.scan_and_process(tmp_path)

    assert len(result) == 2
    file_paths = {pf.file_path for pf in result}
    assert "docs/guide.md" in file_paths
    assert "docs/ref.md" in file_paths


def test_scan_and_process_handles_errors(tmp_path):
    _write_doc(tmp_path / "good.md")

    class _FailProvider(_MockProvider):
        def __init__(self):
            super().__init__()
            self._calls = 0

        def extract_from_chunk(self, chunk_text, heading, source_file):
            self._calls += 1
            if self._calls == 1:
                raise RuntimeError("LLM error")
            return [DocChunkExtraction(key="guide:ok", summary="OK.")]

    _write_doc(tmp_path / "also_good.md")
    ingester = DocRepoIngester(_FailProvider())
    result = ingester.scan_and_process(tmp_path)
    assert len(result) >= 1
    keys = {pf.key for pf in result}
    assert "guide:ok" in keys


def test_scan_files_empty_doc_paths(tmp_path):
    _write_doc(tmp_path / "root.md")
    ingester = DocRepoIngester(_MockProvider(), doc_paths=[])
    files = ingester.scan_files(tmp_path)
    assert files == []


def test_scan_files_nonexistent_doc_path(tmp_path):
    _write_doc(tmp_path / "exists.md")
    ingester = DocRepoIngester(_MockProvider(), doc_paths=["nonexistent"])
    files = ingester.scan_files(tmp_path)
    assert files == []


def test_process_file_empty_document(tmp_path):
    doc = _write_doc(tmp_path / "empty.md", "")
    extractions = [DocChunkExtraction(key="guide:x", summary="X.")]
    ingester = DocRepoIngester(_MockProvider(extractions))
    result = ingester.process_file(doc, tmp_path)
    assert result == []


def test_content_hash_deterministic(tmp_path):
    content = "# Hello\n" + "word " * 100
    doc = _write_doc(tmp_path / "test.md", content)
    extractions = [DocChunkExtraction(key="guide:x", summary="X.")]
    ingester = DocRepoIngester(_MockProvider(extractions))

    r1 = ingester.process_file(doc, tmp_path)
    r2 = ingester.process_file(doc, tmp_path)
    assert r1[0].content_hash == r2[0].content_hash
