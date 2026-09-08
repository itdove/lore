from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lore.ingest.chunker import SUPPORTED_EXTENSIONS
from lore.ingest.doc import extract_doc_chunks
from lore.llm.base import LLMProvider
from lore.sync.parser import ParsedFile, compute_content_hash

log = logging.getLogger("lore.ingest")
DEFAULT_MAX_WORKERS = 4


class DocRepoIngester:
    def __init__(
        self,
        provider: LLMProvider,
        doc_paths: list[str] | None = None,
        exclude_paths: list[str] | None = None,
        max_workers: int = DEFAULT_MAX_WORKERS,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")

        self._provider = provider
        self._doc_paths = doc_paths
        self._exclude_paths = exclude_paths or []
        self._max_workers = max_workers

    def scan_files(self, repo_path: Path) -> list[Path]:
        candidates: list[Path] = []
        repo_resolved = repo_path.resolve()

        if self._doc_paths is not None:
            for dp in self._doc_paths:
                search_dir = repo_path / dp
                if not search_dir.resolve().is_relative_to(repo_resolved):
                    log.warning("Skipping doc_path outside repo: %s", dp)
                    continue
                if search_dir.is_dir():
                    candidates.extend(sorted(search_dir.rglob("*")))
                elif search_dir.is_file():
                    candidates.append(search_dir)
        else:
            candidates = sorted(repo_path.rglob("*"))

        exclude_resolved = [(repo_path / ep).resolve() for ep in self._exclude_paths]

        result: list[Path] = []
        for path in candidates:
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            rel = path.relative_to(repo_path)
            if any(part.startswith(".") for part in rel.parts):
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(repo_resolved):
                continue
            if any(resolved.is_relative_to(ex) for ex in exclude_resolved):
                continue
            result.append(path)

        return result

    def process_file(
        self,
        file_path: Path,
        repo_path: Path,
    ) -> list[ParsedFile]:
        raw = file_path.read_bytes()
        content_hash = compute_content_hash(raw)
        text = raw.decode("utf-8", errors="replace")
        rel = file_path.relative_to(repo_path).as_posix()

        parsed_files: list[ParsedFile] = []
        for ext, tags, _chunk in extract_doc_chunks(
            self._provider, file_path, text=text
        ):
            parsed_files.append(
                ParsedFile(
                    key=ext.key,
                    value=ext.summary,
                    tags=tags,
                    locked=False,
                    created_by=None,
                    projects=None,
                    content_hash=content_hash,
                    file_path=rel,
                )
            )

        return parsed_files

    def scan_and_process(self, repo_path: Path) -> list[ParsedFile]:
        files = sorted(
            self.scan_files(repo_path),
            key=lambda path: path.relative_to(repo_path).as_posix(),
        )
        result: list[ParsedFile] = []

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = [
                (file_path, executor.submit(self.process_file, file_path, repo_path))
                for file_path in files
            ]
            for file_path, future in futures:
                try:
                    result.extend(future.result())
                except Exception:
                    log.warning("Failed to process %s", file_path, exc_info=True)

        return result
