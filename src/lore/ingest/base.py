from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Literal

from lore.store.base import KnowledgeEntry


class LoreIngester(ABC):
    trigger: Literal["hook", "scheduled", "manual"] = "manual"
    review_policy: Literal["immediate", "pr_based"] = "immediate"

    @abstractmethod
    def detect(self, project_dir: Path) -> bool: ...

    @abstractmethod
    def extract_delta(self, since: datetime | None = None) -> list[KnowledgeEntry]: ...

    @abstractmethod
    def transform(self, entries: list[KnowledgeEntry]) -> list[KnowledgeEntry]: ...

    @abstractmethod
    def load(self, entries: list[KnowledgeEntry]) -> None: ...
