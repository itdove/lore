from __future__ import annotations

import os
from pathlib import Path


def config_dir() -> Path:
    if env := os.environ.get("LORE_CONFIG_DIR"):
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "lore"


def data_dir() -> Path:
    if env := os.environ.get("LORE_DATA_DIR"):
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "lore"


def cache_dir() -> Path:
    if env := os.environ.get("LORE_CACHE_DIR"):
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "lore"


def state_dir() -> Path:
    if env := os.environ.get("LORE_STATE_DIR"):
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "lore"


def config_path() -> Path:
    return config_dir() / "config.json"


def db_path() -> Path:
    return data_dir() / "knowledge.db"
