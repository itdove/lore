from __future__ import annotations

import os
import subprocess
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


def sync_state_path() -> Path:
    return state_dir() / "sync-state.json"


def sync_lock_path() -> Path:
    return state_dir() / "sync.lock"


def sync_log_path() -> Path:
    return state_dir() / "sync.md"


def repos_cache_path() -> Path:
    return cache_dir() / "repos"


def is_configured() -> bool:
    return config_path().exists()


def is_project() -> bool:
    return (Path.cwd() / ".lore").is_dir()


_project_remote_cache: dict[str | None, tuple[str | None, str | None]] = {}


def get_project_remote(
    project_path: str | None = None,
) -> tuple[str | None, str | None]:
    """Return (repo_url, default_branch) for a project's git remote.

    Returns (None, None) if no git remote exists.
    Results are cached by project_path for the process lifetime.
    """
    if project_path in _project_remote_cache:
        return _project_remote_cache[project_path]

    cwd = project_path
    try:
        url = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
            timeout=30,
        ).stdout.strip()
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        _project_remote_cache[project_path] = (None, None)
        return None, None

    try:
        ref = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
            timeout=30,
        ).stdout.strip()
        branch = ref.rsplit("/", 1)[-1]
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        branch = "main"

    result = (url, branch)
    _project_remote_cache[project_path] = result
    return result
