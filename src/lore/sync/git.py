from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

_CLONE_TIMEOUT = 300
_FETCH_TIMEOUT = 120
_LOCAL_TIMEOUT = 30


def _redact_url_creds(text: str) -> str:
    return re.sub(r"(https?://)([^@]+)@", r"\1****@", text)


class SyncError(Exception):
    pass


class GitRepoManager:
    def __init__(self, cache_base: Path) -> None:
        self._cache_base = cache_base

    @staticmethod
    def repo_to_url(repo: str) -> str:
        if repo.startswith(("https://", "http://", "git@", "ssh://")):
            return repo
        if repo.startswith(("/", "./", "../", "~")):
            return repo
        return f"https://{repo}"

    @staticmethod
    def repo_dir_hash(repo: str, branch: str) -> str:
        return hashlib.sha256(f"{repo}@{branch}".encode()).hexdigest()[:16]

    def repo_path(self, repo: str, branch: str) -> Path:
        return self._cache_base / self.repo_dir_hash(repo, branch)

    def clone_or_pull(self, repo: str, branch: str) -> str:
        url = self.repo_to_url(repo)
        path = self.repo_path(repo, branch)

        if not path.exists():
            self._cache_base.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--branch",
                        branch,
                        "--single-branch",
                        url,
                        str(path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=_CLONE_TIMEOUT,
                )
            except subprocess.TimeoutExpired as exc:
                raise SyncError(
                    f"Timed out cloning {repo}@{branch} " f"after {_CLONE_TIMEOUT}s"
                ) from exc
            except subprocess.CalledProcessError as exc:
                raise SyncError(
                    f"Failed to clone {repo}@{branch}: "
                    f"{_redact_url_creds(exc.stderr.strip())}"
                ) from exc
        else:
            try:
                subprocess.run(
                    ["git", "-C", str(path), "fetch", "origin", branch],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=_FETCH_TIMEOUT,
                )
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(path),
                        "reset",
                        "--hard",
                        f"origin/{branch}",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=_LOCAL_TIMEOUT,
                )
            except subprocess.TimeoutExpired as exc:
                raise SyncError(f"Timed out syncing {repo}@{branch}") from exc
            except subprocess.CalledProcessError as exc:
                raise SyncError(
                    f"Failed to pull {repo}@{branch}: "
                    f"{_redact_url_creds(exc.stderr.strip())}"
                ) from exc

        return self.get_head_sha(path)

    @staticmethod
    def get_head_sha(repo_path: Path) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=_LOCAL_TIMEOUT,
        )
        return result.stdout.strip()
