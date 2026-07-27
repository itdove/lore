from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HierarchyLevel:
    level: int
    repo: str
    branch: str = "main"
    name: str | None = None
    writable: bool = True
    description: str | None = None


@dataclass
class StoreConfig:
    type: str = "sqlite"
    path: str | None = None


@dataclass
class LLMConfig:
    provider: str = "none"
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None


@dataclass
class SearchConfig:
    embedding_provider: str = "none"
    embedding_model: str | None = None
    embedding_base_url: str | None = None
    dedup_threshold: float = 0.20
    min_similarity: float = 0.3

    def __post_init__(self) -> None:
        if not 0.0 <= self.dedup_threshold <= 1.0:
            raise ValueError(
                f"dedup_threshold must be in [0, 1], got {self.dedup_threshold}"
            )
        if not 0.0 <= self.min_similarity <= 1.0:
            raise ValueError(
                f"min_similarity must be in [0, 1], got {self.min_similarity}"
            )


@dataclass
class GitConfig:
    provider: str = "github"


@dataclass
class SyncConfig:
    auto_sync: bool = True
    staleness_threshold_minutes: int = 60
    on_session_start: bool = True


@dataclass
class CaptureConfig:
    enabled: bool = True
    max_entries_per_session: int = 5
    min_novelty_score: float = 0.3
    auto_store_individual: bool = True
    auto_pr_shared: bool = False


@dataclass
class IngestConfig:
    enabled: bool = True
    disabled_sources: list[str] = field(default_factory=list)


@dataclass
class GlobalConfig:
    projects: list[str] = field(default_factory=list)
    store: StoreConfig = field(default_factory=StoreConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    git: GitConfig = field(default_factory=GitConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    ingest: IngestConfig = field(default_factory=IngestConfig)


@dataclass
class KeyStructure:
    description: str = "Keys use colon-separated segments from general to specific"
    examples: list[str] = field(default_factory=list)


@dataclass
class ProjectConfig:
    hierarchy: list[HierarchyLevel] = field(default_factory=list)
    individual_description: str = (
        "Store here when knowledge is specific to this project or "
        "session: local discoveries, work-in-progress findings, "
        "project-specific patterns not yet validated for the team."
    )
    project_description: str = (
        "Store here when knowledge is project-specific and useful to "
        "anyone working on this project: conventions, gotchas, decisions."
    )
    key_structure: KeyStructure = field(default_factory=KeyStructure)
