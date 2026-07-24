from __future__ import annotations

import argparse
import io
import json
import os
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
        with mock.patch("shutil.which", return_value="/usr/local/bin/lore"):
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

    assert (project_dir / ".mcp.json").exists()
    assert (project_dir / ".claude" / "settings.json").exists()


def test_init_idempotent(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    with mock.patch("lore.cli.input", side_effect=["0"]):
        with mock.patch("shutil.which", return_value="/usr/local/bin/lore"):
            with mock.patch.object(Path, "cwd", return_value=project_dir):
                import argparse

                from lore.cli import _cmd_init

                _cmd_init(argparse.Namespace())

    with mock.patch("lore.cli.input", side_effect=["0"]):
        with mock.patch("shutil.which", return_value="/usr/local/bin/lore"):
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
        with mock.patch("shutil.which", return_value="/usr/local/bin/lore"):
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
        with mock.patch("shutil.which", return_value="/usr/local/bin/lore"):
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
        with mock.patch("shutil.which", return_value="/usr/local/bin/lore"):
            with mock.patch.object(Path, "cwd", return_value=project_dir):
                import argparse

                from lore.cli import _cmd_init

                _cmd_init(argparse.Namespace())

    global_cfg = json.loads(config_path().read_text())
    assert str(project_dir) in global_cfg["lore"]["projects"]


def test_init_registers_mcp(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        with mock.patch("shutil.which", return_value="/usr/local/bin/lore"):
            from lore.cli import _register_mcp

            _register_mcp()

    mcp_json = project_dir / ".mcp.json"
    assert mcp_json.exists()
    data = json.loads(mcp_json.read_text())
    assert data["mcpServers"]["lore"]["command"] == "/usr/local/bin/lore"
    assert data["mcpServers"]["lore"]["args"] == ["mcp-server"]


def test_init_mcp_idempotent(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    mcp_json = project_dir / ".mcp.json"
    mcp_json.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "lore": {"command": "/old/path", "args": ["mcp-server"]},
                    "other": {"command": "other", "args": []},
                }
            }
        )
    )

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        from lore.cli import _register_mcp

        _register_mcp()

    data = json.loads(mcp_json.read_text())
    assert data["mcpServers"]["lore"]["command"] == "/old/path"
    assert "other" in data["mcpServers"]


def test_init_mcp_merges_existing(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    mcp_json = project_dir / ".mcp.json"
    mcp_json.write_text(
        json.dumps({"mcpServers": {"other": {"command": "other", "args": []}}})
    )

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        with mock.patch("shutil.which", return_value="/usr/local/bin/lore"):
            from lore.cli import _register_mcp

            _register_mcp()

    data = json.loads(mcp_json.read_text())
    assert "lore" in data["mcpServers"]
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


# =====================================================================
# lore config show
# =====================================================================


def test_config_show_merged(tmp_path, capsys):
    project_dir = tmp_path / "myproject"
    lore_dir = project_dir / ".lore"
    lore_dir.mkdir(parents=True)

    global_data = {"lore": {"store": {"type": "sqlite"}, "projects": []}}
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps(global_data))

    project_data = {
        "lore": {"hierarchy": [{"level": 1, "repo": "https://x.git", "branch": "main"}]}
    }
    (lore_dir / "config.json").write_text(json.dumps(project_data))

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        import argparse

        from lore.cli import _cmd_config_show

        rc = _cmd_config_show(argparse.Namespace(global_=False, project=False))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["lore"]["store"]["type"] == "sqlite"
    assert len(out["lore"]["hierarchy"]) == 1


def test_config_show_global_only(tmp_path, capsys):
    global_data = {"lore": {"store": {"type": "sqlite"}}}
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps(global_data))

    from lore.cli import _cmd_config_show

    rc = _cmd_config_show(argparse.Namespace(global_=True, project=False))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["lore"]["store"]["type"] == "sqlite"


def test_config_show_project_only(tmp_path, capsys):
    project_dir = tmp_path / "myproject"
    lore_dir = project_dir / ".lore"
    lore_dir.mkdir(parents=True)

    project_data = {"lore": {"hierarchy": []}}
    (lore_dir / "config.json").write_text(json.dumps(project_data))

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        from lore.cli import _cmd_config_show

        rc = _cmd_config_show(argparse.Namespace(global_=False, project=True))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["lore"]["hierarchy"] == []


def test_config_show_project_not_in_lore(tmp_path, capsys):
    bare_dir = tmp_path / "bare"
    bare_dir.mkdir()

    with mock.patch.object(Path, "cwd", return_value=bare_dir):
        from lore.cli import _cmd_config_show

        rc = _cmd_config_show(argparse.Namespace(global_=False, project=True))

    assert rc == 1
    assert "Not in a lore project" in capsys.readouterr().err


# =====================================================================
# lore config set
# =====================================================================


def test_config_set_project(tmp_path, capsys):
    project_dir = tmp_path / "myproject"
    lore_dir = project_dir / ".lore"
    lore_dir.mkdir(parents=True)
    (lore_dir / "config.json").write_text("{}")

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        from lore.cli import _cmd_config_set

        rc = _cmd_config_set(
            argparse.Namespace(
                key="lore.store.path",
                value="/tmp/db.sqlite",
                global_=False,
            )
        )

    assert rc == 0
    data = json.loads((lore_dir / "config.json").read_text())
    assert data["lore"]["store"]["path"] == "/tmp/db.sqlite"


def test_config_set_global(tmp_path, capsys):
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text("{}")

    from lore.cli import _cmd_config_set

    rc = _cmd_config_set(
        argparse.Namespace(key="lore.sync_interval", value="10m", global_=True)
    )

    assert rc == 0
    data = json.loads(config_path().read_text())
    assert data["lore"]["sync_interval"] == "10m"


def test_config_set_parses_types(tmp_path, capsys):
    project_dir = tmp_path / "myproject"
    lore_dir = project_dir / ".lore"
    lore_dir.mkdir(parents=True)
    (lore_dir / "config.json").write_text("{}")

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        from lore.cli import _cmd_config_set

        _cmd_config_set(argparse.Namespace(key="a", value="true", global_=False))
        _cmd_config_set(argparse.Namespace(key="b", value="42", global_=False))
        _cmd_config_set(argparse.Namespace(key="c", value="null", global_=False))
        _cmd_config_set(argparse.Namespace(key="d", value="3.14", global_=False))

    data = json.loads((lore_dir / "config.json").read_text())
    assert data["a"] is True
    assert data["b"] == 42
    assert data["c"] is None
    assert data["d"] == 3.14


def test_config_set_not_in_lore(tmp_path, capsys):
    bare_dir = tmp_path / "bare"
    bare_dir.mkdir()

    with mock.patch.object(Path, "cwd", return_value=bare_dir):
        from lore.cli import _cmd_config_set

        rc = _cmd_config_set(argparse.Namespace(key="lore.x", value="y", global_=False))

    assert rc == 1
    assert "Not in a lore project" in capsys.readouterr().err


# =====================================================================
# lore config edit
# =====================================================================


def test_config_edit_opens_editor(tmp_path, capsys):
    project_dir = tmp_path / "myproject"
    lore_dir = project_dir / ".lore"
    lore_dir.mkdir(parents=True)
    (lore_dir / "config.json").write_text('{"lore": {}}')

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        mock_ret = mock.MagicMock(returncode=0)
        with mock.patch("subprocess.run", return_value=mock_ret) as mock_run:
            with mock.patch.dict(os.environ, {"EDITOR": "nano"}):
                from lore.cli import _cmd_config_edit

                rc = _cmd_config_edit(argparse.Namespace(global_=False))

    assert rc == 0
    cfg = str(lore_dir / "config.json")
    mock_run.assert_called_once_with(["nano", cfg])


def test_config_edit_global(tmp_path, capsys):
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text("{}")

    mock_ret = mock.MagicMock(returncode=0)
    with mock.patch("subprocess.run", return_value=mock_ret) as mock_run:
        with mock.patch.dict(os.environ, {"VISUAL": "code"}):
            from lore.cli import _cmd_config_edit

            rc = _cmd_config_edit(argparse.Namespace(global_=True))

    assert rc == 0
    mock_run.assert_called_once_with(["code", str(config_path())])


def test_config_edit_invalid_json(tmp_path, capsys):
    project_dir = tmp_path / "myproject"
    lore_dir = project_dir / ".lore"
    lore_dir.mkdir(parents=True)
    cfg_file = lore_dir / "config.json"
    cfg_file.write_text('{"lore": {}}')

    def fake_editor(cmd):
        cfg_file.write_text("not valid json {{{")
        return mock.MagicMock(returncode=0)

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        with mock.patch("subprocess.run", side_effect=fake_editor):
            with mock.patch.dict(os.environ, {"EDITOR": "vim"}):
                from lore.cli import _cmd_config_edit

                rc = _cmd_config_edit(argparse.Namespace(global_=False))

    assert rc == 1
    assert "Invalid JSON" in capsys.readouterr().err


def test_config_edit_not_in_lore(tmp_path, capsys):
    bare_dir = tmp_path / "bare"
    bare_dir.mkdir()

    with mock.patch.object(Path, "cwd", return_value=bare_dir):
        from lore.cli import _cmd_config_edit

        rc = _cmd_config_edit(argparse.Namespace(global_=False))

    assert rc == 1
    assert "Not in a lore project" in capsys.readouterr().err


def test_config_edit_creates_file_if_missing(tmp_path, capsys):
    project_dir = tmp_path / "myproject"
    lore_dir = project_dir / ".lore"
    lore_dir.mkdir(parents=True)

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        with mock.patch("subprocess.run", return_value=mock.MagicMock(returncode=0)):
            with mock.patch.dict(os.environ, {"EDITOR": "vi"}):
                from lore.cli import _cmd_config_edit

                rc = _cmd_config_edit(argparse.Namespace(global_=False))

    assert rc == 0
    assert (lore_dir / "config.json").exists()


# =====================================================================
# lore config (no subcommand)
# =====================================================================


def test_config_no_subcommand(capsys):
    from lore.cli import _cmd_config

    rc = _cmd_config(argparse.Namespace(config_command=None))
    assert rc == 1
    assert "Usage" in capsys.readouterr().err


def test_main_config_show_exits_zero(tmp_path, capsys):
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text('{"lore": {}}')

    from lore.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["config", "show", "--global"])

    assert exc_info.value.code == 0


# =====================================================================
# lore hook registration
# =====================================================================


def test_init_registers_hooks(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        from lore.cli import _register_hooks

        _register_hooks()

    settings = project_dir / ".claude" / "settings.json"
    assert settings.exists()
    data = json.loads(settings.read_text())
    hooks = data["hooks"]
    assert any(h["command"] == "lore hook recall" for h in hooks["UserPromptSubmit"])
    assert any(h["command"] == "lore hook nudge" for h in hooks["PostToolUse"])
    assert any(h["command"] == "lore hook capture" for h in hooks["Stop"])


def test_init_hooks_idempotent(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        from lore.cli import _register_hooks

        _register_hooks()
        _register_hooks()

    settings = project_dir / ".claude" / "settings.json"
    data = json.loads(settings.read_text())
    assert len(data["hooks"]["UserPromptSubmit"]) == 1
    assert len(data["hooks"]["PostToolUse"]) == 1
    assert len(data["hooks"]["Stop"]) == 1


def test_init_hooks_merges_existing(tmp_path):
    project_dir = tmp_path / "myproject"
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "settings.json").write_text(
        json.dumps(
            {
                "permissions": {"allow": ["npm test"]},
                "hooks": {
                    "UserPromptSubmit": [
                        {"type": "command", "command": "other-tool hook"}
                    ]
                },
            }
        )
    )

    with mock.patch.object(Path, "cwd", return_value=project_dir):
        from lore.cli import _register_hooks

        _register_hooks()

    data = json.loads((claude_dir / "settings.json").read_text())
    assert data["permissions"]["allow"] == ["npm test"]
    assert len(data["hooks"]["UserPromptSubmit"]) == 2
    assert any(
        h["command"] == "other-tool hook" for h in data["hooks"]["UserPromptSubmit"]
    )


# =====================================================================
# lore hook commands
# =====================================================================


def test_hook_recall_outputs_context(store, capsys):
    store.store(
        _make_entry(
            key="conv:naming",
            value="use snake_case for Python",
            level=1,
            level_name="team",
        )
    )

    payload = json.dumps({"user_message": "snake_case Python"})

    with mock.patch("lore.cli._is_lore_project", return_value=True):
        with mock.patch("lore.cli._get_store", return_value=store):
            with mock.patch(
                "lore.config.manager.get_project_config",
                return_value=mock.MagicMock(hierarchy=[]),
            ):
                with mock.patch("lore.cli._maybe_trigger_auto_sync"):
                    with mock.patch("sys.stdin", io.StringIO(payload)):
                        from lore.cli import _cmd_hook_recall

                        rc = _cmd_hook_recall(argparse.Namespace())

    assert rc == 0
    out = capsys.readouterr().out
    assert "conv:naming" in out
    assert "snake_case" in out
    assert "<lore-context>" in out


def test_hook_recall_empty_stdin(capsys):
    with mock.patch("sys.stdin", io.StringIO("")):
        from lore.cli import _cmd_hook_recall

        rc = _cmd_hook_recall(argparse.Namespace())

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_hook_recall_no_results(store, capsys):
    payload = json.dumps({"user_message": "nonexistent topic"})

    with mock.patch("lore.cli._is_lore_project", return_value=True):
        with mock.patch("lore.cli._get_store", return_value=store):
            with mock.patch(
                "lore.config.manager.get_project_config",
                return_value=mock.MagicMock(hierarchy=[]),
            ):
                with mock.patch("lore.cli._maybe_trigger_auto_sync"):
                    with mock.patch("sys.stdin", io.StringIO(payload)):
                        from lore.cli import _cmd_hook_recall

                        rc = _cmd_hook_recall(argparse.Namespace())

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_hook_nudge_exits_zero():
    from lore.cli import _cmd_hook_nudge

    assert _cmd_hook_nudge(argparse.Namespace()) == 0


def test_hook_capture_exits_zero():
    from lore.cli import _cmd_hook_capture

    assert _cmd_hook_capture(argparse.Namespace()) == 0


def test_hook_recall_invalid_json(capsys):
    with mock.patch("sys.stdin", io.StringIO("not json {{")):
        from lore.cli import _cmd_hook_recall

        rc = _cmd_hook_recall(argparse.Namespace())

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_hook_no_subcommand(capsys):
    from lore.cli import _cmd_hook

    rc = _cmd_hook(argparse.Namespace(hook_command=None))
    assert rc == 1
    assert "Usage" in capsys.readouterr().err


# =====================================================================
# _parse_value edge cases
# =====================================================================


def test_parse_value_json_array():
    from lore.cli import _parse_value

    assert _parse_value("[1, 2, 3]") == [1, 2, 3]


def test_parse_value_json_object():
    from lore.cli import _parse_value

    assert _parse_value('{"key": "val"}') == {"key": "val"}


def test_parse_value_plain_string():
    from lore.cli import _parse_value

    assert _parse_value("hello") == "hello"


def test_parse_value_empty_string():
    from lore.cli import _parse_value

    assert _parse_value("") == ""


# =====================================================================
# lore sync --status
# =====================================================================


def test_sync_status_never_synced(capsys):
    from lore.cli import _cmd_sync_status

    rc = _cmd_sync_status(argparse.Namespace())
    assert rc == 0
    out = capsys.readouterr().out
    assert "Last sync: never" in out
    assert "STALE" in out


def test_sync_status_with_state(tmp_path, capsys):
    from lore.config.utils import state_dir

    state_file = state_dir() / "sync-state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "repos": {
                    "a": {
                        "repo": "r1",
                        "branch": "main",
                        "last_commit": "s1",
                        "last_sync": "2020-01-01T00:00:00+00:00",
                        "file_hashes": {},
                    }
                }
            }
        )
    )

    from lore.cli import _cmd_sync_status

    rc = _cmd_sync_status(argparse.Namespace())
    assert rc == 0
    out = capsys.readouterr().out
    assert "2020-01-01" in out
    assert "STALE" in out
    assert "Auto-sync: enabled" in out


# =====================================================================
# lore sync lock
# =====================================================================


def test_sync_fails_when_locked(capsys):
    import time

    from lore.config.utils import state_dir

    lock_path = state_dir() / "sync.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    import os

    lock_path.write_text(f"{os.getpid()}\n{time.monotonic()}")

    from lore.cli import _cmd_sync

    rc = _cmd_sync(argparse.Namespace(status=False, force=False, verbose=False))
    assert rc == 1
    assert "already in progress" in capsys.readouterr().err


# =====================================================================
# auto-sync trigger
# =====================================================================


def test_auto_sync_triggers_when_stale():
    import subprocess

    from lore.cli import _maybe_trigger_auto_sync

    with mock.patch(
        "lore.config.manager.get_global_config",
        return_value=mock.MagicMock(
            sync=mock.MagicMock(
                auto_sync=True,
                on_session_start=True,
                staleness_threshold_minutes=60,
            )
        ),
    ):
        with mock.patch("lore.sync.lock.SyncLockManager.is_locked", False):
            with mock.patch(
                "lore.sync.state.SyncStateManager.last_sync_time",
                return_value=None,
            ):
                with mock.patch("subprocess.Popen") as mock_popen:
                    _maybe_trigger_auto_sync()

    mock_popen.assert_called_once_with(
        ["lore", "sync"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def test_auto_sync_skips_when_disabled():
    from lore.cli import _maybe_trigger_auto_sync

    with mock.patch(
        "lore.config.manager.get_global_config",
        return_value=mock.MagicMock(
            sync=mock.MagicMock(auto_sync=False, on_session_start=True)
        ),
    ):
        with mock.patch("subprocess.Popen") as mock_popen:
            _maybe_trigger_auto_sync()

    mock_popen.assert_not_called()


def test_auto_sync_skips_when_fresh():
    from datetime import datetime, timezone

    from lore.cli import _maybe_trigger_auto_sync

    fresh = datetime.now(timezone.utc).isoformat()

    with mock.patch(
        "lore.config.manager.get_global_config",
        return_value=mock.MagicMock(
            sync=mock.MagicMock(
                auto_sync=True,
                on_session_start=True,
                staleness_threshold_minutes=60,
            )
        ),
    ):
        with mock.patch("lore.sync.lock.SyncLockManager.is_locked", False):
            with mock.patch(
                "lore.sync.state.SyncStateManager.last_sync_time",
                return_value=fresh,
            ):
                with mock.patch("subprocess.Popen") as mock_popen:
                    _maybe_trigger_auto_sync()

    mock_popen.assert_not_called()


def test_auto_sync_skips_when_locked():
    from lore.cli import _maybe_trigger_auto_sync

    with mock.patch(
        "lore.config.manager.get_global_config",
        return_value=mock.MagicMock(
            sync=mock.MagicMock(
                auto_sync=True,
                on_session_start=True,
                staleness_threshold_minutes=60,
            )
        ),
    ):
        with mock.patch(
            "lore.sync.lock.SyncLockManager.is_locked",
            new_callable=mock.PropertyMock,
            return_value=True,
        ):
            with mock.patch("subprocess.Popen") as mock_popen:
                _maybe_trigger_auto_sync()

    mock_popen.assert_not_called()


def test_auto_sync_never_crashes():
    from lore.cli import _maybe_trigger_auto_sync

    with mock.patch(
        "lore.config.manager.get_global_config",
        side_effect=RuntimeError("config broken"),
    ):
        _maybe_trigger_auto_sync()
