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
        assert gc.sync.auto_sync is True
        assert gc.sync.staleness_threshold_minutes == 60
        assert gc.sync.on_session_start is True


def test_get_global_config_minimal_lore_key(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path)}):
        _clear_config_cache()
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"lore": {}}))
        gc = get_global_config()
        assert gc.projects == []
        assert gc.store.type == "sqlite"
        assert gc.sync.staleness_threshold_minutes == 60


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
                        "sync": {"staleness_threshold_minutes": 5},
                    }
                }
            )
        )
        gc = get_global_config()
        assert gc.projects == ["/home/dev/proj-a"]
        assert gc.llm.provider == "ollama"
        assert gc.llm.model == "phi4-mini"
        assert gc.llm.base_url is None
        assert gc.sync.staleness_threshold_minutes == 5
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
        assert gc.sync.staleness_threshold_minutes == 60


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


def test_get_global_config_sync_object(tmp_path):
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(tmp_path)}):
        _clear_config_cache()
        cfg = tmp_path / "config.json"
        cfg.write_text(
            json.dumps(
                {
                    "lore": {
                        "sync": {
                            "auto_sync": False,
                            "staleness_threshold_minutes": 15,
                            "on_session_start": False,
                        }
                    }
                }
            )
        )
        gc = get_global_config()
        assert gc.sync.auto_sync is False
        assert gc.sync.staleness_threshold_minutes == 15
        assert gc.sync.on_session_start is False


def test_get_global_config_merges_project_llm(tmp_path):
    """Project-level llm config overrides global."""
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    project_dir = tmp_path / "project"
    lore_dir = project_dir / ".lore"
    lore_dir.mkdir(parents=True)

    global_cfg = global_dir / "config.json"
    global_cfg.write_text(
        json.dumps({"lore": {"llm": {"provider": "none", "model": "default"}}})
    )
    project_cfg = lore_dir / "config.json"
    project_cfg.write_text(json.dumps({"lore": {"llm": {"provider": "ollama"}}}))

    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(global_dir)}):
        _clear_config_cache()
        gc = get_global_config(project_dir=project_dir)
        assert gc.llm.provider == "ollama"
        assert gc.llm.model == "default"


def test_get_global_config_search_stays_global(tmp_path):
    """Search config is global-only — project-level search settings ignored."""
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    project_dir = tmp_path / "project"
    lore_dir = project_dir / ".lore"
    lore_dir.mkdir(parents=True)

    global_cfg = global_dir / "config.json"
    global_cfg.write_text(
        json.dumps(
            {
                "lore": {
                    "search": {
                        "embedding_provider": "none",
                        "embedding_model": "global-model",
                    }
                }
            }
        )
    )
    project_cfg = lore_dir / "config.json"
    project_cfg.write_text(
        json.dumps({"lore": {"search": {"embedding_provider": "ollama"}}})
    )

    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(global_dir)}):
        _clear_config_cache()
        gc = get_global_config(project_dir=project_dir)
        assert gc.search.embedding_provider == "none"
        assert gc.search.embedding_model == "global-model"


def test_get_global_config_fallback_no_project_config(tmp_path):
    """Global config used as fallback when project has no config."""
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    global_cfg = global_dir / "config.json"
    global_cfg.write_text(json.dumps({"lore": {"llm": {"provider": "ollama"}}}))

    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(global_dir)}):
        _clear_config_cache()
        gc = get_global_config(project_dir=project_dir)
        assert gc.llm.provider == "ollama"


def test_get_global_config_project_overrides_multiple_sections(tmp_path):
    """Project config can override multiple sections at once."""
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    project_dir = tmp_path / "project"
    lore_dir = project_dir / ".lore"
    lore_dir.mkdir(parents=True)

    global_cfg = global_dir / "config.json"
    global_cfg.write_text(
        json.dumps(
            {
                "lore": {
                    "llm": {"provider": "none"},
                    "search": {"embedding_provider": "none"},
                    "git": {"provider": "github"},
                }
            }
        )
    )
    project_cfg = lore_dir / "config.json"
    project_cfg.write_text(
        json.dumps(
            {
                "lore": {
                    "llm": {"provider": "ollama", "model": "phi4-mini"},
                    "git": {"provider": "gitlab"},
                }
            }
        )
    )

    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(global_dir)}):
        _clear_config_cache()
        gc = get_global_config(project_dir=project_dir)
        assert gc.llm.provider == "ollama"
        assert gc.llm.model == "phi4-mini"
        assert gc.search.embedding_provider == "none"
        assert gc.git.provider == "gitlab"


def test_get_global_config_no_project_dir_uses_cwd(tmp_path, monkeypatch):
    """When project_dir is None, defaults to cwd."""
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    project_dir = tmp_path / "project"
    lore_dir = project_dir / ".lore"
    lore_dir.mkdir(parents=True)

    global_cfg = global_dir / "config.json"
    global_cfg.write_text(json.dumps({"lore": {"llm": {"provider": "none"}}}))
    project_cfg = lore_dir / "config.json"
    project_cfg.write_text(json.dumps({"lore": {"llm": {"provider": "ollama"}}}))

    monkeypatch.chdir(project_dir)
    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(global_dir)}):
        _clear_config_cache()
        gc = get_global_config()
        assert gc.llm.provider == "ollama"


def test_get_global_config_no_cross_project_contamination(tmp_path):
    """Calling with project A then project B must not leak A's values."""
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    proj_a = tmp_path / "a"
    (proj_a / ".lore").mkdir(parents=True)
    proj_b = tmp_path / "b"
    (proj_b / ".lore").mkdir(parents=True)

    (global_dir / "config.json").write_text(
        json.dumps({"lore": {"llm": {"provider": "none", "model": "global"}}})
    )
    (proj_a / ".lore" / "config.json").write_text(
        json.dumps({"lore": {"llm": {"provider": "ollama"}}})
    )
    (proj_b / ".lore" / "config.json").write_text(
        json.dumps({"lore": {"git": {"provider": "gitlab"}}})
    )

    with mock.patch.dict(os.environ, {"LORE_CONFIG_DIR": str(global_dir)}):
        _clear_config_cache()
        gc_a = get_global_config(project_dir=proj_a)
        assert gc_a.llm.provider == "ollama"

        gc_b = get_global_config(project_dir=proj_b)
        assert gc_b.llm.provider == "none"
        assert gc_b.llm.model == "global"
        assert gc_b.git.provider == "gitlab"


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
