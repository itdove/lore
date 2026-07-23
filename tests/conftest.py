import os
from unittest import mock

import pytest

from lore.config import loaders as _loaders


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path):
    config = tmp_path / "config"
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    state = tmp_path / "state"
    config.mkdir()
    data.mkdir()
    cache.mkdir()
    state.mkdir()

    env = {
        "LORE_CONFIG_DIR": str(config),
        "LORE_DATA_DIR": str(data),
        "LORE_CACHE_DIR": str(cache),
        "LORE_STATE_DIR": str(state),
    }
    for var in ("LORE_CONFIG_INLINE", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        if var in os.environ:
            env[var] = ""

    with mock.patch.dict(os.environ, env):
        _loaders._clear_config_cache()
        yield
        _loaders._clear_config_cache()
