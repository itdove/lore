from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from lore.config.manager import get_global_config, get_project_config
from lore.config.models import PROJECT_LEVEL, HierarchyLevel
from lore.config.utils import get_project_remote
from lore.embedding import EmbeddingProvider, get_embedding_provider
from lore.embedding.base import embed_to_blob
from lore.store.base import KnowledgeEntry, StoreBackend
from lore.store.priority import pick_winner
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

        cfg = get_global_config()
        emb_provider: EmbeddingProvider | None = None
        if cfg.search.embedding_provider != "none":
            try:
                emb_provider = get_embedding_provider()
            except Exception:
                logger.warning("Failed to init embedding provider", exc_info=True)

        sync_states = self._state.load()

        self._sync_project_levels(projects, sync_states, emb_provider, result, now)

        repo_levels = self._collect_hierarchy(projects)

        real_states: dict[str, RepoSyncState] | None = None
        if self._state._force:
            real_states = SyncStateManager(self._state._path).load()

        for (repo, branch), hier in repo_levels.items():
            try:
                commit_sha = self._git.clone_or_pull(repo, branch)
            except SyncError as exc:
                result.errors.append(str(exc))
                continue

            result.repos_synced.append(f"{repo}@{branch}")
            repo_hash = GitRepoManager.repo_dir_hash(repo, branch)
            repo_path = self._git.repo_path(repo, branch)

            old_state = sync_states.get(repo_hash)
            if not old_state and hier.ingester and real_states:
                old_state = real_states.get(repo_hash)
            old_hashes = old_state.file_hashes if old_state else None
            parsed_files = self._scan_repo(repo_path, hier, old_hashes)

            self._sync_one_repo(
                parsed_files=parsed_files,
                level=hier.level,
                level_name=hier.name,
                repo_id=repo,
                branch_id=branch,
                commit_sha=commit_sha,
                repo_hash=repo_hash,
                sync_states=sync_states,
                emb_provider=emb_provider,
                result=result,
                now=now,
                ingested_from=hier.ingester or "git",
            )

        promoted = self._store.delete_promoted_locals()
        result.promoted = promoted
        if promoted:
            result.details.append(f"[P] {promoted} local entries promoted")
            self._store.commit()

        self._state.save(sync_states)
        self._log.write(result)
        return result

    def _sync_project_levels(
        self,
        projects: list[str],
        sync_states: dict[str, RepoSyncState],
        emb_provider: EmbeddingProvider | None,
        result: SyncResult,
        now: str,
    ) -> None:
        for project_path in projects:
            repo_url, repo_branch = get_project_remote(project_path)

            if repo_url and repo_branch:
                try:
                    commit_sha = self._git.clone_or_pull(repo_url, repo_branch)
                except SyncError as exc:
                    result.errors.append(str(exc))
                    continue
                cached_path = self._git.repo_path(repo_url, repo_branch)
                knowledge_dir = cached_path / ".lore" / "knowledge"
            else:
                knowledge_dir = Path(project_path) / ".lore" / "knowledge"
                try:
                    commit_sha = GitRepoManager.get_head_sha(Path(project_path))
                except Exception:
                    commit_sha = "unknown"

            if not knowledge_dir.is_dir():
                continue

            repo_id = repo_url or f"local:{project_path}"
            branch_id = repo_branch or "local"

            repo_hash = hashlib.sha256(f"project:{project_path}".encode()).hexdigest()[
                :16
            ]

            result.repos_synced.append(f"project:{Path(project_path).name}")

            self._sync_one_repo(
                parsed_files=scan_repo(knowledge_dir),
                level=PROJECT_LEVEL,
                level_name="project",
                repo_id=repo_id,
                branch_id=branch_id,
                commit_sha=commit_sha,
                repo_hash=repo_hash,
                sync_states=sync_states,
                emb_provider=emb_provider,
                result=result,
                now=now,
            )

    def _scan_repo(
        self,
        repo_path: Path,
        hier: HierarchyLevel,
        old_hashes: dict[str, str] | None = None,
    ) -> list[ParsedFile]:
        if hier.ingester == "doc-repo":
            from lore.ingest.doc_repo import DocRepoIngester
            from lore.llm import get_llm_provider
            from lore.sync.parser import compute_content_hash

            provider = get_llm_provider()
            ingester = DocRepoIngester(
                provider,
                doc_paths=hier.doc_paths,
                exclude_paths=hier.exclude_paths,
            )
            files = ingester.scan_files(repo_path)
            result: list[ParsedFile] = []
            unchanged_files: set[str] = set()
            for f in files:
                rel = f.relative_to(repo_path).as_posix()
                if old_hashes:
                    raw = f.read_bytes()
                    h = compute_content_hash(raw)
                    if old_hashes.get(rel) == h:
                        unchanged_files.add(rel)
                        continue
                try:
                    result.extend(ingester.process_file(f, repo_path))
                except Exception:
                    logger.warning("Failed to process %s", f, exc_info=True)
            if unchanged_files:
                existing = self._store.list_by_repo(hier.repo, hier.branch)
                for entry in existing:
                    if not entry.provenance:
                        continue
                    prov = json.loads(entry.provenance)
                    if prov.get("file_path") in unchanged_files:
                        result.append(
                            ParsedFile(
                                key=entry.key,
                                value=entry.value,
                                tags=entry.tags,
                                locked=entry.locked,
                                created_by=None,
                                projects=entry.projects,
                                content_hash=old_hashes.get(prov["file_path"], ""),
                                file_path=prov["file_path"],
                            )
                        )
            return result
        if hier.ingester is not None:
            logger.warning(
                "Unknown ingester %r for level %s, falling back to default scan",
                hier.ingester,
                hier.name or hier.level,
            )
        return scan_repo(repo_path)

    def _sync_one_repo(
        self,
        parsed_files: list[ParsedFile],
        level: int,
        level_name: str | None,
        repo_id: str,
        branch_id: str,
        commit_sha: str,
        repo_hash: str,
        sync_states: dict[str, RepoSyncState],
        emb_provider: EmbeddingProvider | None,
        result: SyncResult,
        now: str,
        ingested_from: str = "git",
    ) -> None:
        current_keys: set[str] = set()
        new_hashes: dict[str, str] = {}

        old_state = sync_states.get(repo_hash)
        changed: list[ParsedFile] = []
        for pf in parsed_files:
            current_keys.add(pf.key)
            new_hashes[pf.file_path] = pf.content_hash
            if old_state and old_state.file_hashes.get(pf.file_path) == pf.content_hash:
                continue
            changed.append(pf)

        if changed:
            changed_keys = {pf.key for pf in changed}
            conflicts_by_key = self._store.find_conflicts_batch(changed_keys, level)
            embeddings = self._batch_embed(changed, emb_provider)

            for pf in changed:
                entry = self._build_entry(
                    pf,
                    level,
                    level_name,
                    repo_id,
                    branch_id,
                    commit_sha,
                    embeddings.get(pf.key),
                    ingested_from=ingested_from,
                )
                others = conflicts_by_key.get(pf.key, [])
                entry_id, action = self._store.sync_upsert(entry, pre_conflicts=others)
                if action == "blocked":
                    blocker = next(
                        (o for o in others if o.locked and o.level < entry.level),
                        None,
                    )
                    result.blocked += 1
                    if blocker:
                        result.details.append(
                            f"[!] {pf.key} blocked by locked"
                            f" {blocker.level_label} entry"
                        )
                    continue
                if action == "created":
                    result.created += 1
                    result.details.append(f"[+] {pf.key} ({pf.file_path})")
                else:
                    result.updated += 1
                    result.details.append(f"[~] {pf.key} ({pf.file_path})")
                self._resolve_conflicts(entry_id, entry, pf, result, others)

        existing = self._store.list_by_repo(repo_id, branch_id)
        for entry in existing:
            if entry.key not in current_keys:
                self._store.clear_conflict(entry.id)
                self._store.delete_by_source(
                    entry.key,
                    repo_id,
                    branch_id,
                    "file removed from repo",
                    "sync",
                )
                result.deleted += 1
                result.details.append(f"[-] {entry.key}")

        self._store.commit()

        sync_states[repo_hash] = RepoSyncState(
            repo=repo_id,
            branch=branch_id,
            last_commit=commit_sha,
            last_sync=now,
            file_hashes=new_hashes,
        )

    def _collect_hierarchy(
        self, projects: list[str]
    ) -> dict[tuple[str, str], HierarchyLevel]:
        repo_levels: dict[tuple[str, str], HierarchyLevel] = {}
        for project_path in projects:
            try:
                cfg = get_project_config(project_path)
            except Exception as exc:
                logger.warning("Skipping project %s: %s", project_path, exc)
                continue
            for h in cfg.hierarchy:
                key = (h.repo, h.branch)
                if key not in repo_levels or h.level < repo_levels[key].level:
                    repo_levels[key] = h
        return repo_levels

    def _resolve_conflicts(
        self,
        entry_id: str,
        entry: KnowledgeEntry,
        pf: ParsedFile,
        result: SyncResult,
        others: list[KnowledgeEntry],
    ) -> None:
        proxy = KnowledgeEntry(
            id=entry_id,
            key=entry.key,
            value=entry.value,
            level=entry.level,
            locked=entry.locked,
        )
        for other in others:
            winner, loser = pick_winner(proxy, other)
            self._store.apply_conflict(winner.id, loser.id)
            result.conflicts += 1
            result.details.append(
                f"[C] {pf.key} conflicts with {other.level_label} entry"
            )

    def _batch_embed(
        self,
        files: list[ParsedFile],
        emb_provider: EmbeddingProvider | None,
    ) -> dict[str, bytes]:
        if not emb_provider or not files:
            return {}
        texts = [f"{pf.key} {pf.value}" for pf in files]
        result: dict[str, bytes] = {}
        batch_size = 32
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_files = files[i : i + batch_size]
            try:
                vectors = emb_provider.embed_batch(batch_texts)
                for pf, vec in zip(batch_files, vectors):
                    if vec:
                        result[pf.key] = embed_to_blob(vec)
            except Exception:
                logger.warning(
                    "Batch embedding failed for %d files",
                    len(batch_texts),
                    exc_info=True,
                )
        return result

    def _build_entry(
        self,
        parsed: ParsedFile,
        level: int,
        level_name: str | None,
        repo: str,
        branch: str,
        commit_sha: str,
        embedding_blob: bytes | None = None,
        ingested_from: str = "git",
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
            ingested_from=ingested_from,
            provenance=json.dumps(
                {
                    "commit_sha": commit_sha,
                    "file_path": parsed.file_path,
                    "content_hash": parsed.content_hash,
                }
            ),
            projects=parsed.projects,
            embedding=embedding_blob,
        )
