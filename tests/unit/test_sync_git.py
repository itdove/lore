import subprocess
from unittest import mock

import pytest

from lore.sync.git import GitRepoManager, SyncError

# --- repo_to_url ---


def test_repo_to_url_plain():
    assert GitRepoManager.repo_to_url("github.com/org/k") == "https://github.com/org/k"


def test_repo_to_url_already_https():
    assert (
        GitRepoManager.repo_to_url("https://github.com/org/k")
        == "https://github.com/org/k"
    )


def test_repo_to_url_ssh():
    assert (
        GitRepoManager.repo_to_url("git@github.com:org/k.git")
        == "git@github.com:org/k.git"
    )


def test_repo_to_url_http():
    assert (
        GitRepoManager.repo_to_url("http://gitlab.com/org/k")
        == "http://gitlab.com/org/k"
    )


# --- repo_dir_hash ---


def test_repo_dir_hash_deterministic():
    h1 = GitRepoManager.repo_dir_hash("github.com/org/k", "main")
    h2 = GitRepoManager.repo_dir_hash("github.com/org/k", "main")
    assert h1 == h2
    assert len(h1) == 16


def test_repo_dir_hash_different_branches():
    h1 = GitRepoManager.repo_dir_hash("github.com/org/k", "main")
    h2 = GitRepoManager.repo_dir_hash("github.com/org/k", "dev")
    assert h1 != h2


# --- repo_path ---


def test_repo_path_under_cache(tmp_path):
    mgr = GitRepoManager(tmp_path)
    path = mgr.repo_path("github.com/org/k", "main")
    assert path.parent == tmp_path
    assert len(path.name) == 16


# --- clone_or_pull ---


def test_clone_or_pull_clone_new(tmp_path):
    mgr = GitRepoManager(tmp_path)
    repo = "github.com/org/k"
    branch = "main"
    repo_dir = mgr.repo_path(repo, branch)
    assert not repo_dir.exists()

    with mock.patch("lore.sync.git.subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(stdout="abc123\n", returncode=0)
        sha = mgr.clone_or_pull(repo, branch)

    calls = mock_run.call_args_list
    clone_call = calls[0]
    assert "clone" in clone_call.args[0]
    assert "--branch" in clone_call.args[0]
    assert branch in clone_call.args[0]
    assert sha == "abc123"


def test_clone_or_pull_pull_existing(tmp_path):
    mgr = GitRepoManager(tmp_path)
    repo = "github.com/org/k"
    branch = "main"
    repo_dir = mgr.repo_path(repo, branch)
    repo_dir.mkdir(parents=True)

    with mock.patch("lore.sync.git.subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(stdout="def456\n", returncode=0)
        sha = mgr.clone_or_pull(repo, branch)

    calls = mock_run.call_args_list
    assert len(calls) == 3
    assert "fetch" in calls[0].args[0]
    assert "reset" in calls[1].args[0]
    assert "rev-parse" in calls[2].args[0]
    assert sha == "def456"


def test_clone_or_pull_clone_error(tmp_path):
    mgr = GitRepoManager(tmp_path)
    with mock.patch("lore.sync.git.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            128, "git", stderr="fatal: repo not found"
        )
        with pytest.raises(SyncError, match="Failed to clone"):
            mgr.clone_or_pull("github.com/org/bad", "main")


def test_clone_or_pull_pull_error(tmp_path):
    mgr = GitRepoManager(tmp_path)
    repo = "github.com/org/k"
    branch = "main"
    mgr.repo_path(repo, branch).mkdir(parents=True)

    with mock.patch("lore.sync.git.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "git", stderr="error: network"
        )
        with pytest.raises(SyncError, match="Failed to pull"):
            mgr.clone_or_pull(repo, branch)
