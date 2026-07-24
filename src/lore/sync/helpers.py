from __future__ import annotations


def get_sync_status_dict() -> dict:
    from lore.config.manager import get_global_config
    from lore.config.utils import sync_lock_path, sync_state_path
    from lore.sync.lock import SyncLockManager
    from lore.sync.state import SyncStateManager, is_stale

    config = get_global_config()
    state_mgr = SyncStateManager(sync_state_path())
    lock_mgr = SyncLockManager(sync_lock_path())

    last_sync = state_mgr.last_sync_time()
    threshold = config.sync.staleness_threshold_minutes
    stale = is_stale(last_sync, threshold)

    return {
        "last_sync": last_sync,
        "stale": stale,
        "threshold_minutes": threshold,
        "auto_sync": config.sync.auto_sync,
        "locked": lock_mgr.is_locked,
    }


def run_sync(store):
    from lore.config.manager import get_global_config
    from lore.config.utils import (
        repos_cache_path,
        sync_lock_path,
        sync_log_path,
        sync_state_path,
    )
    from lore.sync.engine import SyncEngine
    from lore.sync.git import GitRepoManager
    from lore.sync.lock import SyncLockManager
    from lore.sync.log import SyncLogWriter
    from lore.sync.state import SyncStateManager

    config = get_global_config()
    state_mgr = SyncStateManager(sync_state_path())

    with SyncLockManager(sync_lock_path()):
        git_mgr = GitRepoManager(repos_cache_path())
        log_writer = SyncLogWriter(sync_log_path())
        engine = SyncEngine(store, git_mgr, state_mgr, log_writer)
        return engine.sync_all(config.projects)
