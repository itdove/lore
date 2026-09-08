from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class DocumentChunk:
    text: str
    heading: str
    chunk_index: int
    source_file: str
    word_count: int


_FORMAT_MAP = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "rst",
    ".adoc": "adoc",
    ".txt": "text",
}

SUPPORTED_EXTENSIONS = frozenset(_FORMAT_MAP)


def detect_format(file_path: Path) -> str:
    return _FORMAT_MAP.get(file_path.suffix.lower(), "text")


def _strip_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end + 3 :].lstrip("\n")
    try:
        fm = yaml.safe_load(fm_text)
        if not isinstance(fm, dict):
            fm = {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


def _split_markdown(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []
    in_code = False

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code

        if not in_code and re.match(r"^#{1,6}\s", line):
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body or current_heading:
            sections.append((current_heading, body))

    return sections


_RST_ADORN = re.compile(r"^([=\-~^\"#`\.:'+!_*]{2,})\s*$")


def _split_rst(text: str) -> list[tuple[str, str]]:
    lines = text.split("\n")
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []
    i = 0

    while i < len(lines):
        is_heading = False
        heading_text = ""

        if i + 1 < len(lines) and _RST_ADORN.match(lines[i + 1]):
            adorn = lines[i + 1].strip()
            if len(adorn) >= len(lines[i].rstrip()):
                is_heading = True
                heading_text = lines[i].strip()

        if (
            not is_heading
            and i + 2 < len(lines)
            and _RST_ADORN.match(lines[i])
            and _RST_ADORN.match(lines[i + 2])
        ):
            adorn_top = lines[i].strip()
            adorn_bot = lines[i + 2].strip()
            if adorn_top[0] == adorn_bot[0] and len(adorn_top) >= len(
                lines[i + 1].rstrip()
            ):
                is_heading = True
                heading_text = lines[i + 1].strip()

        if is_heading:
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = heading_text

            if (
                i + 2 < len(lines)
                and _RST_ADORN.match(lines[i])
                and _RST_ADORN.match(lines[i + 2])
            ):
                i += 3
            else:
                i += 2
            current_lines = []
        else:
            current_lines.append(lines[i])
            i += 1

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body or current_heading:
            sections.append((current_heading, body))

    return sections


def _split_adoc(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []

    for line in text.split("\n"):
        if re.match(r"^={1,5}\s", line):
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = line.lstrip("=").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body or current_heading:
            sections.append((current_heading, body))

    return sections


def _split_text(text: str) -> list[tuple[str, str]]:
    paragraphs = re.split(r"\n\n\n+", text)
    sections = [("", p.strip()) for p in paragraphs if p.strip()]
    return sections or [("", "")]


def _word_count(text: str) -> int:
    return len(text.split())


def _merge_small_chunks(
    sections: list[tuple[str, str]], min_words: int
) -> list[tuple[str, str]]:
    if len(sections) <= 1:
        return sections

    merged: list[tuple[str, str]] = [sections[0]]
    for heading, body in sections[1:]:
        if _word_count(body) < min_words and merged:
            prev_heading, prev_body = merged[-1]
            combined = f"{prev_body}\n\n{body}".strip() if prev_body else body
            merged[-1] = (prev_heading, combined)
        else:
            merged.append((heading, body))

    return merged


def _split_large_chunks(
    sections: list[tuple[str, str]], max_words: int
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []

    for heading, body in sections:
        if _word_count(body) <= max_words:
            result.append((heading, body))
            continue

        paragraphs = re.split(r"\n\n+", body)
        current: list[str] = []
        current_wc = 0
        part = 0

        for para in paragraphs:
            pw = _word_count(para)
            if current and current_wc + pw > max_words:
                h = heading if part == 0 else f"{heading} (cont.)"
                result.append((h, "\n\n".join(current)))
                current = [para]
                current_wc = pw
                part += 1
            else:
                current.append(para)
                current_wc += pw

        if current:
            h = heading if part == 0 else f"{heading} (cont.)"
            result.append((h, "\n\n".join(current)))

    return result


_SPLITTERS = {
    "markdown": _split_markdown,
    "rst": _split_rst,
    "adoc": _split_adoc,
    "text": _split_text,
}


def chunk_document(
    file_path: Path,
    *,
    text: str | None = None,
    min_words: int = 100,
    max_words: int = 1000,
) -> list[DocumentChunk]:
    if text is None:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    _, body = _strip_frontmatter(text)

    if not body.strip():
        return []

    fmt = detect_format(file_path)
    splitter = _SPLITTERS[fmt]
    sections = splitter(body)

    if not sections:
        return []

    sections = _merge_small_chunks(sections, min_words)
    sections = _split_large_chunks(sections, max_words)

    source = str(file_path)
    return [
        DocumentChunk(
            text=body_text,
            heading=heading,
            chunk_index=i,
            source_file=source,
            word_count=_word_count(body_text),
        )
        for i, (heading, body_text) in enumerate(sections)
        if body_text.strip()
    ]
