from __future__ import annotations

import json
from unittest import mock

import pytest

from lore.dashboard.state import (
    build_repo_file_url,
    get_dashboard_store,
    load_raw_global_config,
    load_raw_project_config,
    promote_entry,
    reset_store,
    save_global_config,
    save_project_config,
    validate_key,
)
from lore.store.base import KnowledgeEntry


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_store()
    yield
    reset_store()


class TestGetDashboardStore:
    def test_returns_store(self):
        store = get_dashboard_store()
        assert store is not None

    def test_singleton(self):
        s1 = get_dashboard_store()
        s2 = get_dashboard_store()
        assert s1 is s2

    def test_reset_clears_singleton(self):
        s1 = get_dashboard_store()
        reset_store()
        s2 = get_dashboard_store()
        assert s1 is not s2


class TestValidateKey:
    def test_valid_key(self):
        assert validate_key("type:domain:slug") is None

    def test_valid_with_hyphens(self):
        assert validate_key("bug:auth-flow:jwt-expiry") is None

    def test_valid_with_underscores(self):
        assert validate_key("config:db_pool:max_size") is None

    def test_valid_single_segment(self):
        assert validate_key("jwt-leeway") is None

    def test_valid_two_segments(self):
        assert validate_key("bug:jwt") is None

    def test_valid_four_segments(self):
        assert validate_key("a:b:c:d") is None

    def test_invalid_empty(self):
        assert validate_key("") is not None

    def test_invalid_spaces(self):
        assert validate_key("type:do main:slug") is not None

    def test_invalid_special_chars(self):
        assert validate_key("bug:api/jwt") is not None


class TestBuildRepoFileUrl:
    def _entry(self, repo_url=None, repo_branch=None, provenance=None):
        return KnowledgeEntry(
            key="test:key:one",
            value="v",
            level=1,
            repo_url=repo_url,
            repo_branch=repo_branch,
            provenance=json.dumps(provenance) if provenance else None,
        )

    def test_github_url(self):
        entry = self._entry(
            repo_url="https://github.com/org/repo",
            repo_branch="main",
            provenance={"file_path": "docs/test.md"},
        )
        url = build_repo_file_url(entry)
        assert url == "https://github.com/org/repo/blob/main/docs/test.md"

    def test_gitlab_url(self):
        entry = self._entry(
            repo_url="https://gitlab.com/org/repo",
            repo_branch="develop",
            provenance={"file_path": "knowledge/item.md"},
        )
        url = build_repo_file_url(entry)
        assert url == "https://gitlab.com/org/repo/-/blob/develop/knowledge/item.md"

    def test_strips_dot_git(self):
        entry = self._entry(
            repo_url="https://github.com/org/repo.git",
            repo_branch="main",
            provenance={"file_path": "test.md"},
        )
        url = build_repo_file_url(entry)
        assert url == "https://github.com/org/repo/blob/main/test.md"

    def test_no_repo_url_returns_none(self):
        entry = self._entry(provenance={"file_path": "test.md"})
        assert build_repo_file_url(entry) is None

    def test_no_provenance_returns_none(self):
        entry = self._entry(repo_url="https://github.com/org/repo")
        assert build_repo_file_url(entry) is None

    def test_no_file_path_in_provenance(self):
        entry = self._entry(
            repo_url="https://github.com/org/repo",
            provenance={"commit_sha": "abc123"},
        )
        assert build_repo_file_url(entry) is None

    def test_default_branch(self):
        entry = self._entry(
            repo_url="https://github.com/org/repo",
            provenance={"file_path": "test.md"},
        )
        url = build_repo_file_url(entry)
        assert "/blob/main/" in url


class TestConfigReadWrite:
    def test_save_and_load_global(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        with mock.patch(
            "lore.dashboard.state._global_config_path",
            return_value=cfg_path,
        ):
            save_global_config({"lore": {"llm": {"provider": "ollama"}}})
            loaded = load_raw_global_config()
            assert loaded["lore"]["llm"]["provider"] == "ollama"

    def test_save_creates_backup(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text('{"old": true}', encoding="utf-8")
        bak_path = cfg_path.with_suffix(".json.bak")

        with mock.patch(
            "lore.dashboard.state._global_config_path",
            return_value=cfg_path,
        ):
            save_global_config({"new": True})
            assert bak_path.exists()
            assert json.loads(bak_path.read_text()) == {"old": True}

    def test_save_and_load_project(self, tmp_path):
        cfg_path = tmp_path / ".lore" / "config.json"
        with mock.patch(
            "lore.dashboard.state._project_config_path",
            return_value=cfg_path,
        ):
            save_project_config({"lore": {"hierarchy": [{"level": 1, "repo": "x"}]}})
            loaded = load_raw_project_config()
            assert len(loaded["lore"]["hierarchy"]) == 1

    def test_load_missing_returns_empty(self, tmp_path):
        cfg_path = tmp_path / "nonexistent.json"
        with mock.patch(
            "lore.dashboard.state._global_config_path",
            return_value=cfg_path,
        ):
            assert load_raw_global_config() == {}


class TestPromoteEntry:
    def test_rejects_non_level_zero(self):
        entry = KnowledgeEntry(key="k:d:s", value="v", level=1)
        result = promote_entry(entry)
        assert "error" in result

    def test_rejects_no_hierarchy(self):
        entry = KnowledgeEntry(key="k:d:s", value="v", level=0)
        mock_store = mock.Mock()
        mock_store.get_by_key_and_level.return_value = entry
        with (
            mock.patch(
                "lore.dashboard.state.get_dashboard_store",
                return_value=mock_store,
            ),
            mock.patch("lore.config.manager.get_project_config") as mock_cfg,
        ):
            mock_cfg.return_value = mock.Mock(hierarchy=[])
            result = promote_entry(entry)
        assert "error" in result

    def test_rejects_deleted_entry(self):
        entry = KnowledgeEntry(key="k:d:s", value="v", level=0)
        mock_store = mock.Mock()
        mock_store.get_by_key_and_level.return_value = None
        with mock.patch(
            "lore.dashboard.state.get_dashboard_store",
            return_value=mock_store,
        ):
            result = promote_entry(entry)
        assert "error" in result
        assert "no longer exists" in result["error"]

    def test_calls_git_interface(self):
        entry = KnowledgeEntry(
            key="bug:auth:jwt", value="fix it", tags="auth,jwt", level=0
        )

        mock_hierarchy = mock.Mock(
            level=1, repo="https://github.com/org/repo", branch="main", name="team"
        )
        mock_proj_cfg = mock.Mock(hierarchy=[mock_hierarchy])
        mock_global_cfg = mock.Mock()
        mock_global_cfg.git.provider = "github"

        mock_git = mock.Mock()
        mock_git.create_pr.return_value = "https://github.com/org/repo/pull/42"

        mock_store = mock.Mock()
        mock_store.get_by_key_and_level.return_value = entry

        with (
            mock.patch(
                "lore.dashboard.state.get_dashboard_store",
                return_value=mock_store,
            ),
            mock.patch(
                "lore.config.manager.get_project_config",
                return_value=mock_proj_cfg,
            ),
            mock.patch(
                "lore.config.manager.get_global_config",
                return_value=mock_global_cfg,
            ),
            mock.patch(
                "lore.git.get_git_interface",
                return_value=mock_git,
            ),
        ):
            result = promote_entry(entry)

        assert result["pr_url"] == "https://github.com/org/repo/pull/42"
        mock_git.create_pr.assert_called_once()
