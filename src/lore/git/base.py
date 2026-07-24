from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path


class GitError(Exception):
    pass


def redact_url_creds(text: str) -> str:
    return re.sub(r"(https?://)([^@]+)@", r"\1****@", text)


def repo_to_url(repo: str) -> str:
    if repo.startswith(("https://", "http://", "git@", "ssh://")):
        return repo
    if repo.startswith(("/", "./", "../", "~")):
        return repo
    return f"https://{repo}"


def key_to_path(key: str) -> str:
    return key.replace(":", "/") + ".md"


class GitInterface(ABC):
    @abstractmethod
    def clone_or_pull(
        self, repo_url: str, target_dir: Path, branch: str = "main"
    ) -> str:
        """Clone on first call, pull on subsequent. Returns HEAD commit SHA."""
        ...

    @abstractmethod
    def create_pr(
        self,
        repo_url: str,
        file_path: str,
        content: str,
        frontmatter: dict,
        title: str,
        body: str,
        branch: str = "main",
    ) -> str:
        """Create branch, write file, commit, push, open PR. Returns PR URL."""
        ...

    @abstractmethod
    def get_pr_status(self, pr_url: str) -> str:
        """Returns: open, merged, closed."""
        ...
