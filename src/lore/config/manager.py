from __future__ import annotations

import warnings
from pathlib import Path

from lore.config.loaders import (
    deep_merge,
    load_global_config,
    load_project_config,
)
from lore.config.models import (
    GitConfig,
    GlobalConfig,
    HierarchyLevel,
    LLMConfig,
    ProjectConfig,
    SearchConfig,
    StoreConfig,
    SyncConfig,
)

_GLOBAL_ONLY_KEYS: frozenset[str] = frozenset()


def _parse_sub_config(cls, data: dict | None):
    if not data:
        return cls()
    valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
    unknown = {
        k for k in data if k not in valid_fields and not k.startswith("_comment")
    }
    if unknown:
        warnings.warn(
            f"Unknown config fields in {cls.__name__} ignored: {unknown}",
            stacklevel=2,
        )
    return cls(**{k: v for k, v in data.items() if k in valid_fields})


def get_global_config(project_dir: Path | None = None) -> GlobalConfig:
    raw = load_global_config()
    lore = raw.get("lore", {})

    project_raw = load_project_config(project_dir or Path.cwd())
    project_overlay = {
        k: v
        for k, v in project_raw.get("lore", {}).items()
        if k not in _GLOBAL_ONLY_KEYS
    }
    lore = deep_merge(lore, project_overlay)

    return GlobalConfig(
        projects=lore.get("projects", []),
        store=_parse_sub_config(StoreConfig, lore.get("store")),
        llm=_parse_sub_config(LLMConfig, lore.get("llm")),
        search=_parse_sub_config(SearchConfig, lore.get("search")),
        git=_parse_sub_config(GitConfig, lore.get("git")),
        sync=_parse_sub_config(SyncConfig, lore.get("sync")),
    )


def get_project_config(project_dir: str | Path | None = None) -> ProjectConfig:
    if project_dir is None:
        project_dir = Path.cwd()
    else:
        project_dir = Path(project_dir)

    raw = load_project_config(project_dir)
    lore = raw.get("lore", {})
    hierarchy_raw = lore.get("hierarchy", [])

    hierarchy = []
    for entry in hierarchy_raw:
        if "level" not in entry or "repo" not in entry:
            continue
        hierarchy.append(
            HierarchyLevel(
                level=entry["level"],
                repo=entry["repo"],
                branch=entry.get("branch", "main"),
                name=entry.get("name"),
            )
        )

    return ProjectConfig(hierarchy=hierarchy)
