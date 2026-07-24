from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from lore.git.base import redact_url_creds
from lore.git.base import repo_to_url as _repo_to_url

_CLONE_TIMEOUT = 300
_FETCH_TIMEOUT = 120
_LOCAL_TIMEOUT = 30


class SyncError(Exception):
    pass


class GitRepoManager:
    def __init__(self, cache_base: Path) -> None:
        self._cache_base = cache_base

    @staticmethod
    def repo_to_url(repo: str) -> str:
        return _repo_to_url(repo)

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
                    f"{redact_url_creds(exc.stderr.strip())}"
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
                    f"{redact_url_creds(exc.stderr.strip())}"
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
