from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lore.config.utils import config_path


@dataclass
class _ConfigCacheEntry:
    result: Any = None
    global_mtime: float | None = None
    project_mtime: float | None = None
    global_path: str | None = None
    project_path: str | None = None
    inline_value: str | None = None


_caches: dict[str, _ConfigCacheEntry] = {}


def _get_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_global_config_raw() -> dict:
    path = config_path()
    data = _load_json(path)

    inline = os.environ.get("LORE_CONFIG_INLINE")
    if inline:
        try:
            overlay = json.loads(inline)
            data = _deep_merge(data, overlay)
        except json.JSONDecodeError:
            pass

    return data


def _load_project_config_raw(project_dir: Path) -> dict:
    path = project_dir / ".lore" / "config.json"
    return _load_json(path)


def load_global_config() -> dict:
    global_path = config_path()
    global_mtime = _get_mtime(global_path)
    inline_value = os.environ.get("LORE_CONFIG_INLINE")
    cache_key = "__global__"

    if cache_key in _caches:
        entry = _caches[cache_key]
        if (
            entry.global_path == str(global_path)
            and entry.global_mtime == global_mtime
            and entry.inline_value == inline_value
        ):

            return entry.result

    result = _load_global_config_raw()
    _caches[cache_key] = _ConfigCacheEntry(
        result=result,
        global_mtime=global_mtime,
        global_path=str(global_path),
        inline_value=inline_value,
    )
    return result


def load_project_config(project_dir: Path) -> dict:
    project_path = project_dir / ".lore" / "config.json"
    project_mtime = _get_mtime(project_path)
    cache_key = str(project_dir)

    if cache_key in _caches:
        entry = _caches[cache_key]
        if (
            entry.project_path == str(project_path)
            and entry.project_mtime == project_mtime
        ):

            return entry.result

    result = _load_project_config_raw(project_dir)
    _caches[cache_key] = _ConfigCacheEntry(
        result=result,
        project_mtime=project_mtime,
        project_path=str(project_path),
    )
    return result


def _clear_config_cache() -> None:
    _caches.clear()
