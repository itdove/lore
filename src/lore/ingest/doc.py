from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from lore.ingest.base import LoreIngester
from lore.ingest.chunker import SUPPORTED_EXTENSIONS, chunk_document
from lore.ingest.registry import register
from lore.llm.base import LLMProvider
from lore.store.base import KnowledgeEntry, StoreBackend, validate_key

log = logging.getLogger("lore.ingest")


def extract_doc_chunks(provider: LLMProvider, file_path: Path):
    """Chunk file, LLM extract, validate keys. Yields (ext, tags, chunk)."""
    chunks = chunk_document(file_path)
    for chunk in chunks:
        extractions = provider.extract_from_chunk(
            chunk.text, chunk.heading, chunk.source_file
        )
        for ext in extractions:
            if validate_key(ext.key) is not None:
                log.warning("Skipping invalid key from LLM: %s", ext.key)
                continue
            tags = ",".join(ext.tags) if ext.tags else None
            yield ext, tags, chunk


@register
class DocIngester(LoreIngester):
    name = "doc"
    triggers = frozenset({"manual"})
    review_policy = "pr_based"
    auto_detect = False

    def __init__(
        self,
        file_path: Path,
        provider: LLMProvider,
        store: StoreBackend,
        level: int = 0,
        level_name: str | None = None,
    ) -> None:
        super().__init__(store, file_path.parent)
        self._file_path = file_path
        self._provider = provider
        self._level = level
        self._level_name = level_name

    def detect(self, project_dir: Path) -> bool:
        return (
            self._file_path.exists()
            and self._file_path.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    def extract_delta(self, since: datetime | None = None) -> list[KnowledgeEntry]:
        entries: list[KnowledgeEntry] = []

        for ext, tags, chunk in extract_doc_chunks(self._provider, self._file_path):
            provenance = json.dumps(
                {
                    "source_file": chunk.source_file,
                    "chunk_index": chunk.chunk_index,
                    "heading": chunk.heading,
                }
            )
            entries.append(
                KnowledgeEntry(
                    key=ext.key,
                    value=ext.summary,
                    level=self._level,
                    level_name=self._level_name,
                    tags=tags,
                    ingested_from="doc",
                    provenance=provenance,
                )
            )

        return entries


def ingest_file(
    file_path: Path,
    provider: LLMProvider,
    store: StoreBackend,
    level: int = 0,
    level_name: str | None = None,
) -> list[KnowledgeEntry]:
    ingester = DocIngester(file_path, provider, store, level, level_name)
    if not ingester.detect(file_path.parent):
        log.warning("DocIngester cannot detect source: %s", file_path)
        return []
    entries = ingester.extract_delta()
    entries = ingester.transform(entries)
    ingester.load(entries)
    return entries
