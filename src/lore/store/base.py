from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class HistoryRecord:
    id: str
    knowledge_id: str
    action: str
    previous_value: str | None = None
    actor: str | None = None
    reason: str | None = None
    timestamp: str | None = None


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

    @property
    def level_label(self) -> str:
        return self.level_name or f"L{self.level}"


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
    def get_by_key_and_level(self, key: str, level: int) -> KnowledgeEntry | None: ...

    @abstractmethod
    def update(
        self,
        key: str,
        value: str,
        reason: str,
        actor: str,
        *,
        tags: str | None = None,
        level: int | None = None,
    ) -> None: ...

    @abstractmethod
    def delete(
        self, key: str, reason: str, actor: str, *, level: int | None = None
    ) -> None: ...

    @abstractmethod
    def list_entries(
        self, tag: str | None = None, level: int | None = None
    ) -> list[KnowledgeEntry]: ...

    @abstractmethod
    def list_conflicts(self) -> list[KnowledgeEntry]: ...

    @abstractmethod
    def get_history(self, knowledge_id: str) -> list[HistoryRecord]: ...

    @abstractmethod
    def health(self) -> dict: ...

    @abstractmethod
    def get_by_id(self, entry_id: str) -> KnowledgeEntry | None: ...

    @abstractmethod
    def get_by_source(
        self, key: str, repo_url: str, repo_branch: str
    ) -> KnowledgeEntry | None: ...

    @abstractmethod
    def sync_upsert(
        self,
        entry: KnowledgeEntry,
        *,
        pre_conflicts: list[KnowledgeEntry] | None = None,
    ) -> tuple[str, str]: ...

    @abstractmethod
    def list_by_repo(self, repo_url: str, repo_branch: str) -> list[KnowledgeEntry]: ...

    @abstractmethod
    def delete_by_source(
        self,
        key: str,
        repo_url: str,
        repo_branch: str,
        reason: str,
        actor: str,
    ) -> None: ...

    @abstractmethod
    def find_conflicts(self, key: str, level: int) -> list[KnowledgeEntry]: ...

    @abstractmethod
    def find_conflicts_batch(
        self, keys: set[str], level: int
    ) -> dict[str, list[KnowledgeEntry]]: ...

    @abstractmethod
    def apply_conflict(self, winner_id: str, loser_id: str) -> None: ...

    @abstractmethod
    def clear_conflict(self, entry_id: str) -> None: ...

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def delete_promoted_locals(self) -> int: ...
