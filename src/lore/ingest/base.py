from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from lore.store.base import KnowledgeEntry, StoreBackend

log = logging.getLogger("lore.ingest")


class LoreIngester(ABC):
    name: ClassVar[str] = "base"
    triggers: ClassVar[frozenset[str]] = frozenset({"manual"})
    review_policy: ClassVar[str] = "immediate"
    auto_detect: ClassVar[bool] = True

    def __init__(self, store: StoreBackend, project_dir: Path) -> None:
        self._store = store
        self._project_dir = project_dir

    @abstractmethod
    def detect(self, project_dir: Path) -> bool: ...

    @abstractmethod
    def extract_delta(self, since: datetime | None = None) -> list[KnowledgeEntry]: ...

    def transform(self, entries: list[KnowledgeEntry]) -> list[KnowledgeEntry]:
        return entries

    def load(self, entries: list[KnowledgeEntry]) -> None:
        for entry in entries:
            self._store.store(entry)
        self._store.commit()

    def run(self, since: datetime | None = None) -> list[KnowledgeEntry]:
        entries = self.extract_delta(since)
        entries = self.transform(entries)
        entries = self._dedup(entries)
        self.load(entries)
        return entries

    def _dedup(self, entries: list[KnowledgeEntry]) -> list[KnowledgeEntry]:
        try:
            from lore.config.manager import get_global_config
            from lore.embedding import get_embedding_provider
            from lore.embedding.base import embed_to_blob

            cfg = get_global_config()
            if cfg.search.embedding_provider == "none":
                return entries
            provider = get_embedding_provider()
            threshold = cfg.search.dedup_threshold
        except Exception:
            return entries

        kept: list[KnowledgeEntry] = []
        for entry in entries:
            try:
                emb = provider.embed(f"{entry.key} {entry.value}")
                if not emb:
                    kept.append(entry)
                    continue
                dupes = self._store.query_vector(
                    emb, limit=1, min_similarity=1.0 - threshold
                )
                if dupes:
                    closest, dist = dupes[0]
                    if dist < threshold and closest.level == entry.level:
                        log.info(
                            "Dedup skip: %s matches %s (dist=%.4f)",
                            entry.key,
                            closest.key,
                            dist,
                        )
                        continue
                entry.embedding = embed_to_blob(emb)
                kept.append(entry)
            except Exception:
                kept.append(entry)
        return kept
