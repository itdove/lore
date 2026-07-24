from __future__ import annotations

import os
from pathlib import Path


def _xdg_dir(lore_env: str, xdg_env: str, default_subpath: str) -> Path:
    if env := os.environ.get(lore_env):
        return Path(env).expanduser()
    xdg = os.environ.get(xdg_env)
    base = Path(xdg) if xdg else Path.home() / default_subpath
    return base / "lore"


def config_dir() -> Path:
    return _xdg_dir("LORE_CONFIG_DIR", "XDG_CONFIG_HOME", ".config")


def data_dir() -> Path:
    return _xdg_dir("LORE_DATA_DIR", "XDG_DATA_HOME", os.path.join(".local", "share"))


def cache_dir() -> Path:
    return _xdg_dir("LORE_CACHE_DIR", "XDG_CACHE_HOME", ".cache")


def state_dir() -> Path:
    return _xdg_dir("LORE_STATE_DIR", "XDG_STATE_HOME", os.path.join(".local", "state"))


def config_path() -> Path:
    return config_dir() / "config.json"


def db_path() -> Path:
    return data_dir() / "knowledge.db"
