from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from lore.config.utils import config_path, db_path
from lore.store.base import KnowledgeEntry
from lore.store.sqlite import SQLiteStore, create_schema


@pytest.fixture
def store():
    conn = create_schema(":memory:")
    return SQLiteStore(conn)


def _make_entry(**kwargs):
    defaults = {"key": "test:domain:slug", "value": "test value", "level": 0}
    defaults.update(kwargs)
    return KnowledgeEntry(**defaults)


# =====================================================================
# lore init
# =====================================================================


def test_init_creates_dirs_and_configs(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    with mock.patch("lore.cli.input", side_effect=["0"]):
        with mock.patch("lore.cli._register_mcp"):
            with mock.patch.object(Path, "cwd", return_value=project_dir):
                import argparse

                from lore.cli import _cmd_init

                rc = _cmd_init(argparse.Namespace())

    assert rc == 0
    assert config_path().parent.exists()
    assert db_path().exists() or db_path().parent.exists()

    global_cfg = json.loads(config_path().read_text())
    assert str(project_dir) in global_cfg["lore"]["projects"]

    project_cfg_file = project_dir / ".lore" / "config.json"
    assert project_cfg_file.exists()
    project_cfg = json.loads(project_cfg_file.read_text())
    assert project_cfg["lore"]["hierarchy"] == []


def test_init_idempotent(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    with mock.patch("lore.cli.input", side_effect=["0"]):
        with mock.patch("lore.cli._register_mcp"):
            with mock.patch.object(Path, "cwd", return_value=project_dir):
                import argparse

                from lore.cli import _cmd_init

                _cmd_init(argparse.Namespace())

    with mock.patch("lore.cli.input", side_effect=["0"]):
        with mock.patch("lore.cli._register_mcp"):
            with mock.patch.object(Path, "cwd", return_value=project_dir):
                rc = _cmd_init(argparse.Namespace())

    assert rc == 0
    global_cfg = json.loads(config_path().read_text())
    assert global_cfg["lore"]["projects"].count(str(project_dir)) == 1


def test_init_with_hierarchy(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    inputs = ["1", "https://github.com/org/knowledge.git", "main", "team"]
    with mock.patch("lore.cli.input", side_effect=inputs):
        with mock.patch("lore.cli._register_mcp"):
            with mock.patch("lore.cli._cmd_sync", return_value=0):
                with mock.patch.object(Path, "cwd", return_value=project_dir):
                    import argparse

                    from lore.cli import _cmd_init

                    rc = _cmd_init(argparse.Namespace())

    assert rc == 0
    project_cfg = json.loads((project_dir / ".lore" / "config.json").read_text())
    assert len(project_cfg["lore"]["hierarchy"]) == 1
    assert (
        project_cfg["lore"]["hierarchy"][0]["repo"]
        == "https://github.com/org/knowledge.git"
    )
    assert project_cfg["lore"]["hierarchy"][0]["name"] == "team"


def test_init_reuse_hierarchy(tmp_path):
    project_a = tmp_path / "project-a"
    project_a.mkdir()
    (project_a / ".lore").mkdir()
    (project_a / ".lore" / "config.json").write_text(
        json.dumps(
            {
                "lore": {
                    "hierarchy": [
                        {
                            "level": 1,
                            "repo": "https://github.com/org/shared.git",
                            "branch": "main",
                            "name": "org",
                        }
                    ]
                }
            }
        )
    )

    global_cfg_data = {"lore": {"projects": [str(project_a)]}}
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps(global_cfg_data, indent=2))

    project_b = tmp_path / "project-b"
    project_b.mkdir()

    with mock.patch("lore.cli.input", return_value="1"):
        with mock.patch("lore.cli._register_mcp"):
            with mock.patch("lore.cli._cmd_sync", return_value=0):
                with mock.patch.object(Path, "cwd", return_value=project_b):
                    import argparse

                    from lore.cli import _cmd_init

                    rc = _cmd_init(argparse.Namespace())

    assert rc == 0
    project_cfg = json.loads((project_b / ".lore" / "config.json").read_text())
    assert len(project_cfg["lore"]["hierarchy"]) == 1
    assert (
        project_cfg["lore"]["hierarchy"][0]["repo"]
        == "https://github.com/org/shared.git"
    )


def test_init_registers_project(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    with mock.patch("lore.cli.input", side_effect=["0"]):
        with mock.patch("lore.cli._register_mcp"):
            with mock.patch.object(Path, "cwd", return_value=project_dir):
                import argparse

                from lore.cli import _cmd_init

                _cmd_init(argparse.Namespace())

    global_cfg = json.loads(config_path().read_text())
    assert str(project_dir) in global_cfg["lore"]["projects"]


def test_init_registers_mcp(tmp_path):
    claude_json = tmp_path / ".claude.json"

    with mock.patch("lore.cli.Path.home", return_value=tmp_path):
        with mock.patch("shutil.which", return_value="/usr/local/bin/lore"):
            from lore.cli import _register_mcp

            _register_mcp()

    data = json.loads(claude_json.read_text())
    assert data["mcpServers"]["lore"]["command"] == "/usr/local/bin/lore"
    assert data["mcpServers"]["lore"]["args"] == ["mcp-server"]


def test_init_mcp_idempotent(tmp_path):
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "lore": {"command": "/old/path", "args": ["mcp-server"]},
                    "other": {"command": "other", "args": []},
                }
            }
        )
    )

    with mock.patch("lore.cli.Path.home", return_value=tmp_path):
        from lore.cli import _register_mcp

        _register_mcp()

    data = json.loads(claude_json.read_text())
    assert data["mcpServers"]["lore"]["command"] == "/old/path"
    assert "other" in data["mcpServers"]


# =====================================================================
# lore search
# =====================================================================


def test_search_returns_results(store, capsys):
    store.store(
        _make_entry(
            key="bug:auth:jwt",
            value="JWT expiry off by one",
            level=1,
            level_name="team",
        )
    )

    with mock.patch("lore.cli._get_store", return_value=store):
        with mock.patch(
            "lore.config.manager.get_project_config",
            return_value=mock.MagicMock(hierarchy=[]),
        ):
            import argparse

            from lore.cli import _cmd_search

            rc = _cmd_search(argparse.Namespace(topic="JWT"))

    assert rc == 0
    out = capsys.readouterr().out
    assert "bug:auth:jwt" in out
    assert "team" in out


def test_search_no_results(store, capsys):
    with mock.patch("lore.cli._get_store", return_value=store):
        with mock.patch(
            "lore.config.manager.get_project_config",
            return_value=mock.MagicMock(hierarchy=[]),
        ):
            import argparse

            from lore.cli import _cmd_search

            rc = _cmd_search(argparse.Namespace(topic="nonexistent"))

    assert rc == 0
    assert "No results" in capsys.readouterr().out


def test_search_priority_resolution(store, capsys):
    store.store(
        _make_entry(
            key="conv:naming", value="use camelCase", level=1, level_name="team"
        )
    )
    store.store(
        _make_entry(
            key="conv:naming", value="use snake_case", level=2, level_name="org"
        )
    )

    with mock.patch("lore.cli._get_store", return_value=store):
        with mock.patch(
            "lore.config.manager.get_project_config",
            return_value=mock.MagicMock(hierarchy=[]),
        ):
            import argparse

            from lore.cli import _cmd_search

            rc = _cmd_search(argparse.Namespace(topic="naming"))

    assert rc == 0
    out = capsys.readouterr().out
    assert "snake_case" in out
    assert out.count("conv:naming") == 1


# =====================================================================
# lore conflicts
# =====================================================================


def test_conflicts_none(store, capsys):
    with mock.patch("lore.cli._get_store", return_value=store):
        import argparse

        from lore.cli import _cmd_conflicts

        rc = _cmd_conflicts(argparse.Namespace())

    assert rc == 0
    assert "No conflicts" in capsys.readouterr().out


def test_conflicts_shows_entries(store, capsys):
    store.store(
        _make_entry(
            key="conv:naming",
            value="use camelCase",
            level=1,
            conflict_with="fake-id",
            conflict_status="unresolved",
        )
    )

    with mock.patch("lore.cli._get_store", return_value=store):
        import argparse

        from lore.cli import _cmd_conflicts

        rc = _cmd_conflicts(argparse.Namespace())

    assert rc == 0
    out = capsys.readouterr().out
    assert "conv:naming" in out
    assert "unresolved" in out
    assert "1 conflict(s)" in out


# =====================================================================
# Exit codes
# =====================================================================


def test_main_no_command(capsys):
    from lore.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 1


def test_main_search_exits_zero(store):
    with mock.patch("lore.cli._get_store", return_value=store):
        with mock.patch(
            "lore.config.manager.get_project_config",
            return_value=mock.MagicMock(hierarchy=[]),
        ):
            from lore.cli import main

            with pytest.raises(SystemExit) as exc_info:
                main(["search", "anything"])

    assert exc_info.value.code == 0


def test_main_conflicts_exits_zero(store):
    with mock.patch("lore.cli._get_store", return_value=store):
        from lore.cli import main

        with pytest.raises(SystemExit) as exc_info:
            main(["conflicts"])

    assert exc_info.value.code == 0
