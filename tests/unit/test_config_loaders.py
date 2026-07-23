import json
import os
import time
from unittest import mock

from lore.config.loaders import (
    _clear_config_cache,
    _deep_merge,
    _load_json,
    load_global_config,
    load_project_config,
)


def test_load_json_missing_file(tmp_path):
    assert _load_json(tmp_path / "nope.json") == {}


def test_load_json_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert _load_json(bad) == {}


def test_load_json_valid(tmp_path):
    f = tmp_path / "ok.json"
    f.write_text('{"a": 1}')
    assert _load_json(f) == {"a": 1}


def test_deep_merge_scalars():
    assert _deep_merge({"a": 1}, {"a": 2}) == {"a": 2}


def test_deep_merge_nested():
    base = {"a": {"b": 1, "c": 2}}
    override = {"a": {"c": 3, "d": 4}}
    assert _deep_merge(base, override) == {"a": {"b": 1, "c": 3, "d": 4}}


def test_deep_merge_new_keys():
    assert _deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_load_global_config_missing_file():
    result = load_global_config()
    assert result == {}


def test_load_global_config_valid(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path)}):
        _clear_config_cache()
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"lore": {"projects": ["/a"]}}))
        result = load_global_config()
        assert result == {"lore": {"projects": ["/a"]}}


def test_load_global_config_inline_overlay(tmp_path):
    with mock.patch.dict(
        os.environ,
        {
            "LORE_CONFIG_DIR": str(tmp_path),
            "LORE_CONFIG_INLINE": json.dumps({"lore": {"sync_interval": "5m"}}),
        },
    ):
        _clear_config_cache()
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"lore": {"projects": ["/a"]}}))
        result = load_global_config()
        assert result["lore"]["projects"] == ["/a"]
        assert result["lore"]["sync_interval"] == "5m"


def test_load_global_config_inline_invalid_json(tmp_path):
    with mock.patch.dict(
        os.environ,
        {
            "LORE_CONFIG_DIR": str(tmp_path),
            "LORE_CONFIG_INLINE": "not json",
        },
    ):
        _clear_config_cache()
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"lore": {"projects": ["/a"]}}))
        result = load_global_config()
        assert result == {"lore": {"projects": ["/a"]}}


def test_load_project_config_missing(tmp_path):
    result = load_project_config(tmp_path)
    assert result == {}


def test_load_project_config_valid(tmp_path):
    lore_dir = tmp_path / ".lore"
    lore_dir.mkdir()
    cfg = lore_dir / "config.json"
    cfg.write_text(
        json.dumps({"lore": {"hierarchy": [{"level": 1, "repo": "github.com/org/k"}]}})
    )
    result = load_project_config(tmp_path)
    assert result["lore"]["hierarchy"][0]["level"] == 1


def test_mtime_cache_hit(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path)}):
        _clear_config_cache()
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"lore": {"projects": ["/a"]}}))

        r1 = load_global_config()
        r2 = load_global_config()
        assert r1 is r2


def test_mtime_cache_miss_on_change(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path)}):
        _clear_config_cache()
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"lore": {"projects": ["/a"]}}))

        r1 = load_global_config()

        time.sleep(0.05)
        cfg.write_text(json.dumps({"lore": {"projects": ["/a", "/b"]}}))

        r2 = load_global_config()
        assert r2["lore"]["projects"] == ["/a", "/b"]
        assert r1 is not r2


def test_clear_config_cache_forces_reload(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path)}):
        _clear_config_cache()
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"lore": {"projects": ["/a"]}}))

        r1 = load_global_config()
        _clear_config_cache()
        r2 = load_global_config()
        assert r1 is not r2
        assert r1 == r2


def test_lore_config_dir_override(tmp_path):
    custom = tmp_path / "custom_dir"
    custom.mkdir()
    cfg = custom / "config.json"
    cfg.write_text(json.dumps({"lore": {"projects": ["/custom"]}}))

    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(custom)}):
        _clear_config_cache()
        result = load_global_config()
        assert result["lore"]["projects"] == ["/custom"]
