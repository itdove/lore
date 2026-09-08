from __future__ import annotations

from lore.ingest.chunker import (
    DocumentChunk,
    _merge_small_chunks,
    _split_adoc,
    _split_large_chunks,
    _split_markdown,
    _split_rst,
    _split_text,
    _strip_frontmatter,
    chunk_document,
    detect_format,
)


def test_detect_format_markdown(tmp_path):
    assert detect_format(tmp_path / "doc.md") == "markdown"
    assert detect_format(tmp_path / "doc.markdown") == "markdown"


def test_detect_format_rst(tmp_path):
    assert detect_format(tmp_path / "doc.rst") == "rst"


def test_detect_format_adoc(tmp_path):
    assert detect_format(tmp_path / "doc.adoc") == "adoc"


def test_detect_format_txt(tmp_path):
    assert detect_format(tmp_path / "doc.txt") == "text"
    assert detect_format(tmp_path / "doc.csv") == "text"


def test_strip_frontmatter_present():
    text = "---\ntitle: Test\ntags: [a, b]\n---\nBody content here."
    fm, body = _strip_frontmatter(text)
    assert fm["title"] == "Test"
    assert fm["tags"] == ["a", "b"]
    assert body == "Body content here."


def test_strip_frontmatter_absent():
    text = "Just a document.\nNo frontmatter."
    fm, body = _strip_frontmatter(text)
    assert fm == {}
    assert body == text


def test_strip_frontmatter_invalid_yaml():
    text = "---\n: bad: yaml:\n---\nBody."
    fm, body = _strip_frontmatter(text)
    assert fm == {}
    assert body == "Body."


def test_split_markdown_by_headings():
    text = "Intro text.\n\n# Chapter 1\nContent one.\n\n## Section 1.1\nSub content."
    sections = _split_markdown(text)
    assert len(sections) == 3
    assert sections[0] == ("", "Intro text.")
    assert sections[1] == ("Chapter 1", "Content one.")
    assert sections[2] == ("Section 1.1", "Sub content.")


def test_split_markdown_no_headings():
    text = "Just a paragraph.\n\nAnother paragraph."
    sections = _split_markdown(text)
    assert len(sections) == 1
    assert sections[0][0] == ""
    assert "Just a paragraph." in sections[0][1]


def test_split_markdown_preserves_code_blocks():
    text = (
        "# Real Heading\nBefore.\n\n"
        "```python\n# This is a comment, not a heading\n"
        "def foo():\n    pass\n```\n\nAfter."
    )
    sections = _split_markdown(text)
    assert len(sections) == 1
    assert "# This is a comment" in sections[0][1]


def test_split_rst_by_sections():
    text = (
        "Intro.\n\nChapter 1\n=========\n"
        "Content one.\n\nSection 1.1\n-----------\nSub content."
    )
    sections = _split_rst(text)
    assert len(sections) == 3
    assert sections[0] == ("", "Intro.")
    assert sections[1][0] == "Chapter 1"
    assert "Content one." in sections[1][1]
    assert sections[2][0] == "Section 1.1"


def test_split_rst_overline_heading():
    text = "=========\nChapter 1\n=========\nContent here."
    sections = _split_rst(text)
    assert len(sections) == 1
    assert sections[0][0] == "Chapter 1"
    assert "Content here." in sections[0][1]


def test_split_rst_no_sections():
    text = "Plain rst content.\n\nMore content."
    sections = _split_rst(text)
    assert len(sections) == 1
    assert "Plain rst content." in sections[0][1]


def test_split_adoc_by_headings():
    text = "Intro.\n\n= Chapter 1\nContent one.\n\n== Section 1.1\nSub content."
    sections = _split_adoc(text)
    assert len(sections) == 3
    assert sections[0] == ("", "Intro.")
    assert sections[1][0] == "Chapter 1"
    assert sections[2][0] == "Section 1.1"


def test_split_text_by_paragraphs():
    text = "First paragraph.\n\n\nSecond paragraph.\n\n\nThird paragraph."
    sections = _split_text(text)
    assert len(sections) == 3
    assert sections[0][1] == "First paragraph."
    assert sections[1][1] == "Second paragraph."


def test_merge_small_chunks():
    sections = [
        ("Heading 1", "word " * 50),
        ("Heading 2", "tiny"),
        ("Heading 3", "word " * 200),
    ]
    merged = _merge_small_chunks(sections, min_words=100)
    assert len(merged) == 2
    assert merged[0][0] == "Heading 1"
    assert "tiny" in merged[0][1]
    assert merged[1][0] == "Heading 3"


def test_merge_preserves_first_chunk():
    sections = [
        ("", "small"),
        ("Big", "word " * 200),
    ]
    merged = _merge_small_chunks(sections, min_words=100)
    assert len(merged) == 2


def test_split_large_chunks():
    big_para_1 = "word " * 600
    big_para_2 = "text " * 600
    sections = [("Heading", f"{big_para_1}\n\n{big_para_2}")]
    result = _split_large_chunks(sections, max_words=1000)
    assert len(result) == 2
    assert result[0][0] == "Heading"
    assert result[1][0] == "Heading (cont.)"


def test_chunk_document_end_to_end(tmp_path):
    doc = tmp_path / "test.md"
    doc.write_text(
        "---\ntitle: Test\n---\n\n"
        "# Introduction\n"
        + "This is content. " * 60
        + "\n\n## Details\n"
        + "More details here. " * 60
    )
    chunks = chunk_document(doc)
    assert len(chunks) >= 2
    assert all(isinstance(c, DocumentChunk) for c in chunks)
    assert chunks[0].chunk_index == 0
    assert chunks[0].source_file == str(doc)
    assert chunks[0].word_count > 0


def test_chunk_document_uses_supplied_text(tmp_path):
    doc = tmp_path / "not-on-disk.md"
    text = "# Supplied content\n" + "word " * 100

    chunks = chunk_document(doc, text=text)

    assert chunks[0].heading == "Supplied content"
    assert chunks[0].text.startswith("word")


def test_chunk_document_empty_file(tmp_path):
    doc = tmp_path / "empty.md"
    doc.write_text("")
    chunks = chunk_document(doc)
    assert chunks == []


def test_chunk_document_no_frontmatter(tmp_path):
    doc = tmp_path / "nofm.md"
    doc.write_text("# Title\nSome content without frontmatter.\n" + "word " * 100)
    chunks = chunk_document(doc)
    assert len(chunks) >= 1
    assert chunks[0].heading == "Title"


def test_chunk_document_rst(tmp_path):
    doc = tmp_path / "test.rst"
    doc.write_text(
        "Chapter\n=======\n"
        + "Content here. " * 60
        + "\n\nSection\n-------\n"
        + "More content. " * 60
    )
    chunks = chunk_document(doc)
    assert len(chunks) >= 2


def test_chunk_document_txt(tmp_path):
    doc = tmp_path / "test.txt"
    doc.write_text(
        "First block.\n" + "word " * 100 + "\n\n\nSecond block.\n" + "word " * 100
    )
    chunks = chunk_document(doc)
    assert len(chunks) >= 1
