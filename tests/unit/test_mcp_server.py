from __future__ import annotations

import importlib.resources
from unittest.mock import patch

import pytest

from lore.mcp.server import _load_lore_instructions, create_server


class TestLoadLoreInstructions:
    def test_loads_from_dot_lore_dir(self, tmp_path, monkeypatch):
        lore_dir = tmp_path / ".lore"
        lore_dir.mkdir()
        lore_md = lore_dir / "LORE.md"
        lore_md.write_text("custom instructions")
        monkeypatch.chdir(tmp_path)

        result = _load_lore_instructions()
        assert result == "custom instructions"

    def test_falls_back_to_bundled(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        result = _load_lore_instructions()
        bundled = importlib.resources.read_text("lore.mcp.skills", "LORE.md")
        assert result == bundled

    def test_bundled_contains_level_guidance(self):
        bundled = importlib.resources.read_text("lore.mcp.skills", "LORE.md")
        assert "Level selection" in bundled
        assert "individual" in bundled
        assert "team" in bundled
        assert "product" in bundled
        assert "org" in bundled


class TestCreateServer:
    def test_returns_fastmcp_instance(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from mcp.server.fastmcp import FastMCP

        server = create_server()
        assert isinstance(server, FastMCP)
        assert server.name == "lore"

    def test_server_has_instructions(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        server = create_server()
        assert server.instructions is not None
        assert "Lore Protocol" in server.instructions


class TestCli:
    def test_mcp_server_subcommand_parsed(self):
        from lore.cli import main

        with patch("lore.cli._cmd_mcp_server", return_value=0) as mock_cmd:
            with pytest.raises(SystemExit) as exc_info:
                main(["mcp-server"])
            mock_cmd.assert_called_once()
            assert exc_info.value.code == 0

    def test_no_subcommand_exits(self):
        from lore.cli import main

        with pytest.raises(SystemExit):
            main([])
