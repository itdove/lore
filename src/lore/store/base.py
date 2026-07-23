from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class KnowledgeEntry:
    key: str
    value: str
    level: int
    id: str = ""
    tags: str | None = None
    level_name: str | None = None
    locked: bool = False
    conflict_with: str | None = None
    conflict_status: str | None = None
    repo_url: str | None = None
    repo_branch: str | None = None
    ingested_from: str | None = None
    provenance: str | None = None
    times_seen: int = 1
    projects: str | None = None
    embedding: bytes | None = None
    created_at: str | None = None
    updated_at: str | None = None


class StoreBackend(ABC):
    @abstractmethod
    def store(self, entry: KnowledgeEntry) -> str: ...

    @abstractmethod
    def query_fts(
        self,
        topic: str,
        limit: int = 10,
        filter_levels: list[int] | None = None,
        filter_repos: list[tuple[str, str]] | None = None,
    ) -> list[KnowledgeEntry]: ...

    @abstractmethod
    def get(self, key: str) -> KnowledgeEntry | None: ...

    @abstractmethod
    def update(self, key: str, value: str, reason: str, actor: str) -> None: ...

    @abstractmethod
    def delete(self, key: str, reason: str, actor: str) -> None: ...

    @abstractmethod
    def list_entries(
        self, tag: str | None = None, level: int | None = None
    ) -> list[KnowledgeEntry]: ...

    @abstractmethod
    def list_conflicts(self) -> list[KnowledgeEntry]: ...

    @abstractmethod
    def health(self) -> dict: ...
