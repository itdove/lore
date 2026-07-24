from __future__ import annotations

from lore.git.base import (
    GitError,
    GitInterface,
    key_to_path,
    redact_url_creds,
    repo_to_url,
)


def get_git_interface(provider: str = "github") -> GitInterface:
    if provider == "github":
        from lore.git.github import GitHubInterface

        return GitHubInterface()
    raise ValueError(f"Unknown git provider: {provider!r}. Available: ['github']")


__all__ = [
    "GitInterface",
    "GitError",
    "get_git_interface",
    "key_to_path",
    "redact_url_creds",
    "repo_to_url",
]
