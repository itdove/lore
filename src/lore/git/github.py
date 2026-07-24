from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import yaml

from lore.git.base import GitError, GitInterface, redact_url_creds, repo_to_url

logger = logging.getLogger(__name__)

_CLONE_TIMEOUT = 300
_PUSH_TIMEOUT = 120
_LOCAL_TIMEOUT = 30
_GH_TIMEOUT = 60


def key_to_branch(key: str) -> str:
    slug = key.replace(":", "-")
    ts = int(time.time())
    return f"lore/{slug}-{ts}"


def build_markdown(frontmatter: dict, body: str) -> str:
    lines = ["---"]
    if frontmatter:
        lines.append(yaml.safe_dump(frontmatter, default_flow_style=False).rstrip())
    lines.append("---")
    lines.append("")
    lines.append(body)
    if not body.endswith("\n"):
        lines.append("")
    return "\n".join(lines)


def _run_git(args: list[str], cwd: Path, timeout: int = _LOCAL_TIMEOUT) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd)] + args,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]} timed out after {timeout}s") from exc
    except subprocess.CalledProcessError as exc:
        raise GitError(
            f"git {args[0]} failed: {redact_url_creds(exc.stderr.strip())}"
        ) from exc


def _run_gh(args: list[str], timeout: int = _GH_TIMEOUT) -> str:
    try:
        result = subprocess.run(
            ["gh"] + args,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"gh {args[0]} timed out after {timeout}s") from exc
    except subprocess.CalledProcessError as exc:
        raise GitError(
            f"gh {args[0]} failed: {redact_url_creds(exc.stderr.strip())}"
        ) from exc


class GitHubInterface(GitInterface):
    def clone_or_pull(
        self, repo_url: str, target_dir: Path, branch: str = "main"
    ) -> str:
        url = repo_to_url(repo_url)
        if not target_dir.exists():
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--branch",
                        branch,
                        "--single-branch",
                        url,
                        str(target_dir),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=_CLONE_TIMEOUT,
                )
            except subprocess.TimeoutExpired as exc:
                raise GitError(f"Timed out cloning {repo_url}@{branch}") from exc
            except subprocess.CalledProcessError as exc:
                raise GitError(
                    f"Failed to clone {repo_url}@{branch}: "
                    f"{redact_url_creds(exc.stderr.strip())}"
                ) from exc
        else:
            _run_git(["fetch", "origin", branch], cwd=target_dir, timeout=_PUSH_TIMEOUT)
            _run_git(
                ["reset", "--hard", f"origin/{branch}"],
                cwd=target_dir,
            )

        return _run_git(["rev-parse", "HEAD"], cwd=target_dir)

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
        url = repo_to_url(repo_url)

        cache_dir = Path.home() / ".cache" / "lore" / "pr-workdirs"
        cache_dir.mkdir(parents=True, exist_ok=True)

        work_dir = Path(tempfile.mkdtemp(dir=cache_dir))
        try:
            self.clone_or_pull(repo_url, work_dir, branch)

            pr_branch = key_to_branch(file_path.replace("/", ":").removesuffix(".md"))
            _run_git(["checkout", "-b", pr_branch], cwd=work_dir)

            target_file = work_dir / file_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            md_content = build_markdown(frontmatter, content)
            target_file.write_text(md_content)

            _run_git(["add", file_path], cwd=work_dir)
            _run_git(["commit", "-m", title], cwd=work_dir)
            _run_git(
                ["push", "origin", pr_branch],
                cwd=work_dir,
                timeout=_PUSH_TIMEOUT,
            )

            pr_url = _run_gh(
                [
                    "pr",
                    "create",
                    "--repo",
                    url,
                    "--base",
                    branch,
                    "--head",
                    pr_branch,
                    "--title",
                    title,
                    "--body",
                    body,
                ]
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        return pr_url

    def get_pr_status(self, pr_url: str) -> str:
        raw = _run_gh(["pr", "view", pr_url, "--json", "state", "--jq", ".state"])
        return raw.lower()
