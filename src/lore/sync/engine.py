from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from lore.config.manager import get_project_config
from lore.store.base import KnowledgeEntry, StoreBackend
from lore.sync.git import GitRepoManager, SyncError
from lore.sync.log import SyncLogWriter, SyncResult
from lore.sync.parser import ParsedFile, scan_repo
from lore.sync.state import RepoSyncState, SyncStateManager

logger = logging.getLogger("lore.sync")


class SyncEngine:
    def __init__(
        self,
        store: StoreBackend,
        git_manager: GitRepoManager,
        state_manager: SyncStateManager,
        log_writer: SyncLogWriter,
    ) -> None:
        self._store = store
        self._git = git_manager
        self._state = state_manager
        self._log = log_writer

    def sync_all(self, projects: list[str]) -> SyncResult:
        now = datetime.now(timezone.utc).isoformat()
        result = SyncResult(timestamp=now)

        repo_levels = self._collect_hierarchy(projects)
        if not repo_levels:
            self._log.write(result)
            return result

        sync_states = self._state.load()

        for (repo, branch), (level, level_name) in repo_levels.items():
            try:
                commit_sha = self._git.clone_or_pull(repo, branch)
            except SyncError as exc:
                result.errors.append(str(exc))
                continue

            result.repos_synced.append(f"{repo}@{branch}")
            repo_hash = GitRepoManager.repo_dir_hash(repo, branch)
            repo_path = self._git.repo_path(repo, branch)

            parsed_files = scan_repo(repo_path)
            current_keys: set[str] = set()
            new_hashes: dict[str, str] = {}

            for pf in parsed_files:
                current_keys.add(pf.key)
                new_hashes[pf.file_path] = pf.content_hash

                old_state = sync_states.get(repo_hash)
                if (
                    old_state
                    and old_state.file_hashes.get(pf.file_path) == pf.content_hash
                ):
                    continue

                entry = self._build_entry(
                    pf, level, level_name, repo, branch, commit_sha
                )
                entry_id, action = self._store.sync_upsert(entry)
                if action == "created":
                    result.created += 1
                    result.details.append(f"[+] {pf.key} ({pf.file_path})")
                else:
                    result.updated += 1
                    result.details.append(f"[~] {pf.key} ({pf.file_path})")

            existing = self._store.list_by_repo(repo, branch)
            for entry in existing:
                if entry.key not in current_keys:
                    self._store.delete_by_source(
                        entry.key, repo, branch, "file removed from repo", "sync"
                    )
                    result.deleted += 1
                    result.details.append(f"[-] {entry.key}")

            sync_states[repo_hash] = RepoSyncState(
                repo=repo,
                branch=branch,
                last_commit=commit_sha,
                last_sync=now,
                file_hashes=new_hashes,
            )

        promoted = self._store.delete_promoted_locals()
        result.promoted = promoted
        if promoted:
            result.details.append(f"[P] {promoted} local entries promoted")

        self._state.save(sync_states)
        self._log.write(result)
        return result

    def _collect_hierarchy(
        self, projects: list[str]
    ) -> dict[tuple[str, str], tuple[int, str | None]]:
        repo_levels: dict[tuple[str, str], tuple[int, str | None]] = {}
        for project_path in projects:
            try:
                cfg = get_project_config(project_path)
            except Exception as exc:
                logger.warning("Skipping project %s: %s", project_path, exc)
                continue
            for h in cfg.hierarchy:
                key = (h.repo, h.branch)
                if key not in repo_levels or h.level < repo_levels[key][0]:
                    repo_levels[key] = (h.level, h.name)
        return repo_levels

    def _build_entry(
        self,
        parsed: ParsedFile,
        level: int,
        level_name: str | None,
        repo: str,
        branch: str,
        commit_sha: str,
    ) -> KnowledgeEntry:
        return KnowledgeEntry(
            key=parsed.key,
            value=parsed.value,
            level=level,
            level_name=level_name,
            tags=parsed.tags,
            locked=parsed.locked,
            repo_url=repo,
            repo_branch=branch,
            ingested_from="git",
            provenance=json.dumps(
                {
                    "commit_sha": commit_sha,
                    "file_path": parsed.file_path,
                    "content_hash": parsed.content_hash,
                }
            ),
            projects=parsed.projects,
        )
