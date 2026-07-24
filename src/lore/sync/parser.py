from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ParsedFile:
    key: str
    value: str
    tags: str | None
    locked: bool
    created_by: str | None
    projects: str | None
    content_hash: str
    file_path: str


def path_to_key(rel_path: str) -> str:
    p = rel_path.replace("\\", "/")
    for ext in (".markdown", ".md"):
        if p.endswith(ext):
            p = p[: -len(ext)]
            break
    return p.replace("/", ":")


def parse_markdown(file_path: Path, repo_root: Path) -> ParsedFile:
    raw = file_path.read_bytes()
    content_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8", errors="replace")

    rel = file_path.relative_to(repo_root).as_posix()
    key = path_to_key(rel)

    frontmatter: dict = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                frontmatter = {}
            body = parts[2].lstrip("\n")

    tags_raw = frontmatter.get("tags")
    tags = ",".join(str(t) for t in tags_raw) if isinstance(tags_raw, list) else None

    projects_raw = frontmatter.get("projects")
    projects = (
        ",".join(str(p) for p in projects_raw)
        if isinstance(projects_raw, list)
        else None
    )

    return ParsedFile(
        key=key,
        value=body,
        tags=tags,
        locked=bool(frontmatter.get("lock", False)),
        created_by=frontmatter.get("created_by"),
        projects=projects,
        content_hash=content_hash,
        file_path=rel,
    )


_SKIP_ROOT_NAMES = {"README.md", "readme.md", "lore.yml", "lore.yaml"}


def scan_repo(repo_root: Path) -> list[ParsedFile]:
    results = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".md", ".markdown"):
            continue
        rel = path.relative_to(repo_root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if len(rel.parts) == 1 and rel.name in _SKIP_ROOT_NAMES:
            continue
        results.append(parse_markdown(path, repo_root))
    return results
