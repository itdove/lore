import os
from pathlib import Path
from unittest import mock

from lore.config.utils import (
    cache_dir,
    config_dir,
    config_path,
    data_dir,
    db_path,
    state_dir,
)


def test_config_dir_uses_lore_config_dir_env(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path / "custom")}):
        assert config_dir() == tmp_path / "custom"


def test_config_dir_uses_xdg_config_home(tmp_path):
    env = {"XDG_CONFIG_HOME": str(tmp_path / "xdg")}
    with mock.patch.dict(os.environ, env, clear=False):
        os.environ.pop("LORE_CONFIG_DIR", None)
        assert config_dir() == tmp_path / "xdg" / "lore"


def test_config_dir_default(tmp_path):
    with mock.patch.dict(os.environ, {}, clear=True):
        result = config_dir()
        assert result == Path.home() / ".config" / "lore"


def test_data_dir_uses_env(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_DATA_DIR": str(tmp_path / "d")}):
        assert data_dir() == tmp_path / "d"


def test_data_dir_uses_xdg(tmp_path):
    env = {"XDG_DATA_HOME": str(tmp_path / "xdg")}
    with mock.patch.dict(os.environ, env, clear=False):
        os.environ.pop("LORE_DATA_DIR", None)
        assert data_dir() == tmp_path / "xdg" / "lore"


def test_cache_dir_uses_env(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CACHE_DIR": str(tmp_path / "c")}):
        assert cache_dir() == tmp_path / "c"


def test_cache_dir_uses_xdg(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path / "xdg")}
    with mock.patch.dict(os.environ, env, clear=False):
        os.environ.pop("LORE_CACHE_DIR", None)
        assert cache_dir() == tmp_path / "xdg" / "lore"


def test_state_dir_uses_env(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_STATE_DIR": str(tmp_path / "s")}):
        assert state_dir() == tmp_path / "s"


def test_state_dir_uses_xdg(tmp_path):
    env = {"XDG_STATE_HOME": str(tmp_path / "xdg")}
    with mock.patch.dict(os.environ, env, clear=False):
        os.environ.pop("LORE_STATE_DIR", None)
        assert state_dir() == tmp_path / "xdg" / "lore"


def test_config_path(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path)}):
        assert config_path() == tmp_path / "config.json"


def test_db_path(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_DATA_DIR": str(tmp_path)}):
        assert db_path() == tmp_path / "knowledge.db"
