from __future__ import annotations

import logging
from pathlib import Path
from typing import Type

from lore.ingest.base import LoreIngester
from lore.store.base import StoreBackend

log = logging.getLogger("lore.ingest")

_REGISTRY: dict[str, Type[LoreIngester]] = {}


def register(cls: Type[LoreIngester]) -> Type[LoreIngester]:
    _REGISTRY[cls.name] = cls
    return cls


def get_ingester(name: str, store: StoreBackend, project_dir: Path) -> LoreIngester:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown ingester: {name!r}. " f"Available: {', '.join(sorted(_REGISTRY))}"
        )
    return cls(store=store, project_dir=project_dir)


def detect_ingesters(
    project_dir: Path,
    store: StoreBackend,
    disabled_sources: list[str] | None = None,
) -> list[LoreIngester]:
    detected = []
    disabled = set(disabled_sources or [])
    for name, cls in sorted(_REGISTRY.items()):
        if not cls.auto_detect:
            continue
        if name in disabled:
            log.debug("Ingester %s disabled by config", name)
            continue
        try:
            ingester = cls(store=store, project_dir=project_dir)
            if ingester.detect(project_dir):
                detected.append(ingester)
        except Exception:
            log.debug("Ingester %s failed detection", name, exc_info=True)
    return detected


def list_ingesters() -> list[str]:
    return sorted(_REGISTRY)
