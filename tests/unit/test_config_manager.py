import json
import os
from unittest import mock

from lore.config.loaders import _clear_config_cache
from lore.config.manager import get_global_config, get_project_config


def test_get_global_config_defaults(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path)}):
        _clear_config_cache()
        gc = get_global_config()
        assert gc.projects == []
        assert gc.store.type == "sqlite"
        assert gc.store.path is None
        assert gc.llm.provider == "none"
        assert gc.llm.model is None
        assert gc.search.embedding_provider == "none"
        assert gc.git.provider == "github"
        assert gc.sync_interval == "30m"


def test_get_global_config_minimal_lore_key(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path)}):
        _clear_config_cache()
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"lore": {}}))
        gc = get_global_config()
        assert gc.projects == []
        assert gc.store.type == "sqlite"
        assert gc.sync_interval == "30m"


def test_get_global_config_partial_overrides(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path)}):
        _clear_config_cache()
        cfg = tmp_path / "config.json"
        cfg.write_text(
            json.dumps(
                {
                    "lore": {
                        "projects": ["/home/dev/proj-a"],
                        "llm": {"provider": "ollama", "model": "phi4-mini"},
                        "sync_interval": "5m",
                    }
                }
            )
        )
        gc = get_global_config()
        assert gc.projects == ["/home/dev/proj-a"]
        assert gc.llm.provider == "ollama"
        assert gc.llm.model == "phi4-mini"
        assert gc.llm.base_url is None
        assert gc.sync_interval == "5m"
        assert gc.store.type == "sqlite"


def test_get_global_config_full(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path)}):
        _clear_config_cache()
        cfg = tmp_path / "config.json"
        cfg.write_text(
            json.dumps(
                {
                    "lore": {
                        "projects": ["/a", "/b"],
                        "store": {"type": "sqlite", "path": "/custom/db"},
                        "llm": {
                            "provider": "ollama",
                            "model": "phi4-mini",
                            "base_url": "http://localhost:11434",
                            "api_key_env": None,
                        },
                        "search": {
                            "embedding_provider": "ollama",
                            "embedding_model": "nomic",
                        },
                        "git": {"provider": "gitlab"},
                        "sync_interval": "1h",
                    }
                }
            )
        )
        gc = get_global_config()
        assert gc.projects == ["/a", "/b"]
        assert gc.store.path == "/custom/db"
        assert gc.llm.base_url == "http://localhost:11434"
        assert gc.search.embedding_provider == "ollama"
        assert gc.git.provider == "gitlab"
        assert gc.sync_interval == "1h"


def test_get_project_config_missing(tmp_path):
    pc = get_project_config(tmp_path)
    assert pc.hierarchy == []


def test_get_project_config_empty_hierarchy(tmp_path):
    lore_dir = tmp_path / ".lore"
    lore_dir.mkdir()
    cfg = lore_dir / "config.json"
    cfg.write_text(json.dumps({"lore": {"hierarchy": []}}))
    pc = get_project_config(tmp_path)
    assert pc.hierarchy == []


def test_get_project_config_with_hierarchy(tmp_path):
    lore_dir = tmp_path / ".lore"
    lore_dir.mkdir()
    cfg = lore_dir / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "lore": {
                    "hierarchy": [
                        {
                            "level": 1,
                            "name": "team",
                            "repo": "github.com/org/k",
                            "branch": "team",
                        },
                        {
                            "level": 2,
                            "name": "product",
                            "repo": "github.com/org/k",
                            "branch": "product",
                        },
                        {
                            "level": 3,
                            "name": "company",
                            "repo": "github.com/org/k",
                            "branch": "org",
                        },
                    ]
                }
            }
        )
    )
    pc = get_project_config(tmp_path)
    assert len(pc.hierarchy) == 3
    assert pc.hierarchy[0].level == 1
    assert pc.hierarchy[0].name == "team"
    assert pc.hierarchy[0].repo == "github.com/org/k"
    assert pc.hierarchy[0].branch == "team"
    assert pc.hierarchy[2].level == 3
    assert pc.hierarchy[2].branch == "org"


def test_get_project_config_defaults_branch(tmp_path):
    lore_dir = tmp_path / ".lore"
    lore_dir.mkdir()
    cfg = lore_dir / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "lore": {
                    "hierarchy": [
                        {"level": 1, "repo": "github.com/team/knowledge"},
                    ]
                }
            }
        )
    )
    pc = get_project_config(tmp_path)
    assert pc.hierarchy[0].branch == "main"
    assert pc.hierarchy[0].name is None


def test_get_project_config_skips_invalid_entries(tmp_path):
    lore_dir = tmp_path / ".lore"
    lore_dir.mkdir()
    cfg = lore_dir / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "lore": {
                    "hierarchy": [
                        {"level": 1, "repo": "github.com/org/k"},
                        {"level": 2},
                        {"repo": "missing-level"},
                        {"level": 3, "repo": "github.com/org/k2"},
                    ]
                }
            }
        )
    )
    pc = get_project_config(tmp_path)
    assert len(pc.hierarchy) == 2
    assert pc.hierarchy[0].level == 1
    assert pc.hierarchy[1].level == 3


def test_projects_array_readable(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path)}):
        _clear_config_cache()
        cfg = tmp_path / "config.json"
        cfg.write_text(
            json.dumps({"lore": {"projects": ["/home/dev/proj-a", "/home/dev/proj-b"]}})
        )
        gc = get_global_config()
        assert len(gc.projects) == 2
        assert "/home/dev/proj-a" in gc.projects
        assert "/home/dev/proj-b" in gc.projects
