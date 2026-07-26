from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from lore.ingest.base import LoreIngester
from lore.ingest.chunker import SUPPORTED_EXTENSIONS, chunk_document
from lore.llm.base import LLMProvider
from lore.store.base import KnowledgeEntry, StoreBackend, validate_key

log = logging.getLogger("lore.ingest")


class DocIngester(LoreIngester):
    trigger = "manual"
    review_policy = "pr_based"

    def __init__(
        self,
        file_path: Path,
        provider: LLMProvider,
        store: StoreBackend,
        level: int = 0,
        level_name: str | None = None,
    ) -> None:
        self._file_path = file_path
        self._provider = provider
        self._store = store
        self._level = level
        self._level_name = level_name

    def detect(self, project_dir: Path) -> bool:
        return (
            self._file_path.exists()
            and self._file_path.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    def extract_delta(self, since: datetime | None = None) -> list[KnowledgeEntry]:
        chunks = chunk_document(self._file_path)
        entries: list[KnowledgeEntry] = []

        for chunk in chunks:
            extractions = self._provider.extract_from_chunk(
                chunk.text, chunk.heading, chunk.source_file
            )
            for ext in extractions:
                if validate_key(ext.key) is not None:
                    log.warning("Skipping invalid key from LLM: %s", ext.key)
                    continue

                provenance = json.dumps(
                    {
                        "source_file": chunk.source_file,
                        "chunk_index": chunk.chunk_index,
                        "heading": chunk.heading,
                    }
                )
                tags = ",".join(ext.tags) if ext.tags else None

                entries.append(
                    KnowledgeEntry(
                        key=ext.key,
                        value=ext.summary,
                        level=self._level,
                        level_name=self._level_name,
                        tags=tags,
                        ingested_from="doc-ingester",
                        provenance=provenance,
                    )
                )

        return entries

    def transform(self, entries: list[KnowledgeEntry]) -> list[KnowledgeEntry]:
        return entries

    def load(self, entries: list[KnowledgeEntry]) -> None:
        for entry in entries:
            self._store.store(entry)
        self._store.commit()


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
