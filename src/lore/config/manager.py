from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path

from lore.config.loaders import (
    deep_merge,
    load_global_config,
    load_project_config,
)
from lore.config.models import (
    IMPLICIT_LEVELS,
    CaptureConfig,
    GitConfig,
    GlobalConfig,
    HierarchyLevel,
    IngestConfig,
    KeyStructure,
    LLMConfig,
    ProjectConfig,
    SearchConfig,
    StoreConfig,
    SyncConfig,
)

logger = logging.getLogger(__name__)

GLOBAL_ONLY_SUBKEYS: frozenset[str] = frozenset(
    {
        "store.path",
        "store.type",
        "search.embedding_provider",
        "search.embedding_model",
        "search.embedding_base_url",
    }
)


def _strip_global_only(overlay: dict) -> dict:
    found = []
    result = {}
    for section, values in overlay.items():
        if not isinstance(values, dict):
            result[section] = values
            continue
        filtered = {}
        for k, v in values.items():
            subkey = f"{section}.{k}"
            if subkey in GLOBAL_ONLY_SUBKEYS:
                found.append(subkey)
            else:
                filtered[k] = v
        if filtered:
            result[section] = filtered
    if found:
        keys_str = ", ".join(sorted(found))
        warnings.warn(
            f"Project config contains global-only settings: {keys_str}. "
            "Use 'lore config set' to move them to global config.",
            stacklevel=3,
        )
    return result


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
    project_lore = project_raw.get("lore", {})
    project_overlay = _strip_global_only(project_lore)
    lore = deep_merge(lore, project_overlay)

    capture = _parse_sub_config(CaptureConfig, lore.get("capture"))
    env_capture = os.environ.get("LORE_CAPTURE")
    if env_capture is not None:
        capture.enabled = env_capture not in ("0", "false", "no")

    return GlobalConfig(
        projects=lore.get("projects", []),
        store=_parse_sub_config(StoreConfig, lore.get("store")),
        llm=_parse_sub_config(LLMConfig, lore.get("llm")),
        search=_parse_sub_config(SearchConfig, lore.get("search")),
        git=_parse_sub_config(GitConfig, lore.get("git")),
        sync=_parse_sub_config(SyncConfig, lore.get("sync")),
        capture=capture,
        ingest=_parse_sub_config(IngestConfig, lore.get("ingest")),
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
        if entry["level"] in IMPLICIT_LEVELS:
            logger.warning(
                "Skipping hierarchy entry with level %d (repo=%s): "
                "levels 0-1 reserved for implicit individual/project",
                entry["level"],
                entry.get("repo", "unknown"),
            )
            continue
        hierarchy.append(
            HierarchyLevel(
                level=entry["level"],
                repo=entry["repo"],
                branch=entry.get("branch", "main"),
                name=entry.get("name"),
                writable=entry.get("writable", True),
                description=entry.get("description"),
                ingester=entry.get("ingester"),
                doc_paths=entry.get("doc_paths"),
                exclude_paths=entry.get("exclude_paths"),
            )
        )

    ks_raw = lore.get("key_structure", {})
    key_structure = KeyStructure(
        description=ks_raw.get(
            "description",
            "Keys use colon-separated segments from general to specific",
        ),
        examples=ks_raw.get("examples", []),
    )

    return ProjectConfig(
        hierarchy=hierarchy,
        individual_description=lore.get(
            "individual_description",
            "Personal notes, local discoveries, work-in-progress findings.",
        ),
        project_description=lore.get(
            "project_description",
            "Project-specific knowledge useful to any teammate on this project.",
        ),
        key_structure=key_structure,
    )
