from __future__ import annotations

import subprocess
from unittest import mock

import pytest

from lore.git import GitError, GitInterface, get_git_interface, key_to_path
from lore.git.base import redact_url_creds, repo_to_url
from lore.git.github import (
    GitHubInterface,
    build_markdown,
    key_to_branch,
)

# --- ABC ---


def test_git_interface_is_abstract():
    with pytest.raises(TypeError):
        GitInterface()


def test_github_interface_is_git_interface():
    assert issubclass(GitHubInterface, GitInterface)


# --- get_git_interface factory ---


def test_get_git_interface_github():
    iface = get_git_interface("github")
    assert isinstance(iface, GitHubInterface)


def test_get_git_interface_unknown():
    with pytest.raises(ValueError, match="Unknown git provider"):
        get_git_interface("gitlab")


# --- key_to_path ---


def test_key_to_path_simple():
    assert key_to_path("bug:auth:jwt-expiry") == "bug/auth/jwt-expiry.md"


def test_key_to_path_single_segment():
    assert key_to_path("topic:a:b") == "topic/a/b.md"


# --- key_to_branch ---


def test_key_to_branch_format():
    branch = key_to_branch("bug:auth:jwt-expiry")
    assert branch.startswith("lore/bug-auth-jwt-expiry-")
    ts_part = branch.split("-")[-1]
    assert ts_part.isdigit()


# --- build_markdown ---


def test_build_markdown_basic():
    fm = {"tags": ["auth", "jwt"], "created_by": "lore-agent"}
    body = "JWT tokens should expire after 1 hour."
    result = build_markdown(fm, body)
    assert result.startswith("---\n")
    assert "created_by: lore-agent" in result
    assert "auth" in result
    assert "jwt" in result
    assert body in result
    assert result.endswith("\n")


def test_build_markdown_body_with_newline():
    result = build_markdown({}, "hello\n")
    assert result == "---\n---\n\nhello\n"


def test_build_markdown_body_without_newline():
    result = build_markdown({}, "hello")
    assert result == "---\n---\n\nhello\n"


# --- clone_or_pull ---


def test_clone_or_pull_clones_new(tmp_path):
    iface = GitHubInterface()
    target = tmp_path / "repo"

    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(stdout="abc123\n", returncode=0)
        sha = iface.clone_or_pull("github.com/org/repo", target, "main")

    assert sha == "abc123"
    calls = mock_run.call_args_list
    assert calls[0][0][0][0] == "git"
    assert "clone" in calls[0][0][0]


def test_clone_or_pull_pulls_existing(tmp_path):
    iface = GitHubInterface()
    target = tmp_path / "repo"
    target.mkdir()

    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(stdout="def456\n", returncode=0)
        sha = iface.clone_or_pull("github.com/org/repo", target, "main")

    assert sha == "def456"
    call_cmds = [c[0][0] for c in mock_run.call_args_list]
    assert any("fetch" in cmd for cmd in call_cmds)


def test_clone_or_pull_clone_error(tmp_path):
    iface = GitHubInterface()
    target = tmp_path / "repo"

    with mock.patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "git", stderr="fatal: not found"
        )
        with pytest.raises(GitError, match="Failed to clone"):
            iface.clone_or_pull("github.com/org/repo", target, "main")


def test_clone_or_pull_timeout(tmp_path):
    iface = GitHubInterface()
    target = tmp_path / "repo"

    with mock.patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired("git", 300)
        with pytest.raises(GitError, match="Timed out cloning"):
            iface.clone_or_pull("github.com/org/repo", target, "main")


# --- create_pr ---


def test_create_pr_calls_sequence(tmp_path):
    iface = GitHubInterface()
    calls = []

    def mock_run(cmd, **kwargs):
        calls.append(cmd)
        result = mock.Mock(stdout="", returncode=0)
        if cmd[0] == "gh" and cmd[1] == "pr":
            result.stdout = "https://github.com/org/repo/pull/42\n"
        elif "rev-parse" in cmd:
            result.stdout = "abc123\n"
        return result

    with (
        mock.patch("subprocess.run", side_effect=mock_run),
        mock.patch(
            "lore.git.github.GitHubInterface.clone_or_pull", return_value="abc123"
        ),
    ):
        pr_url = iface.create_pr(
            repo_url="github.com/org/repo",
            file_path="bug/auth/jwt.md",
            content="JWT fix",
            frontmatter={"tags": ["auth"]},
            title="lore: add bug:auth:jwt",
            body="Auto-generated",
            branch="main",
        )

    assert pr_url == "https://github.com/org/repo/pull/42"
    git_cmds = [c for c in calls if c[0] == "git"]
    gh_cmds = [c for c in calls if c[0] == "gh"]
    assert any("checkout" in c for c in git_cmds)
    assert any("add" in c for c in git_cmds)
    assert any("commit" in c for c in git_cmds)
    assert any("push" in c for c in git_cmds)
    assert len(gh_cmds) == 1
    assert "pr" in gh_cmds[0]


# --- get_pr_status ---


def test_get_pr_status_open():
    iface = GitHubInterface()
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(stdout="OPEN\n", returncode=0)
        assert iface.get_pr_status("https://github.com/org/repo/pull/1") == "open"


def test_get_pr_status_merged():
    iface = GitHubInterface()
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(stdout="MERGED\n", returncode=0)
        assert iface.get_pr_status("https://github.com/org/repo/pull/1") == "merged"


def test_get_pr_status_closed():
    iface = GitHubInterface()
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(stdout="CLOSED\n", returncode=0)
        assert iface.get_pr_status("https://github.com/org/repo/pull/1") == "closed"


def test_get_pr_status_error():
    iface = GitHubInterface()
    with mock.patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "gh", stderr="not found"
        )
        with pytest.raises(GitError, match="gh pr failed"):
            iface.get_pr_status("https://github.com/org/repo/pull/999")


# --- GitError ---


def test_git_error_is_exception():
    assert issubclass(GitError, Exception)
    err = GitError("test")
    assert str(err) == "test"


# --- redact_url_creds (shared from base) ---


def testredact_url_creds_strips_token():
    assert (
        redact_url_creds("https://tok@github.com/o/r") == "https://****@github.com/o/r"
    )


def testredact_url_creds_no_creds():
    assert redact_url_creds("no-creds-here") == "no-creds-here"


def testredact_url_creds_complex():
    assert (
        redact_url_creds("https://user:pass@github.com/o/r")
        == "https://****@github.com/o/r"
    )


# --- repo_to_url (shared from base) ---


def testrepo_to_url_shorthand():
    assert repo_to_url("github.com/org/repo") == "https://github.com/org/repo"


def testrepo_to_url_full_https():
    assert repo_to_url("https://github.com/org/repo") == "https://github.com/org/repo"


def testrepo_to_url_ssh():
    assert repo_to_url("git@github.com:org/repo") == "git@github.com:org/repo"


def testrepo_to_url_local_path():
    assert repo_to_url("/local/path") == "/local/path"
