import json
from datetime import datetime, timedelta, timezone

from lore.sync.state import SyncStateManager, is_stale


def test_is_stale_none_timestamp():
    assert is_stale(None, 60) is True


def test_is_stale_old_timestamp():
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert is_stale(old, 60) is True


def test_is_stale_fresh_timestamp():
    fresh = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert is_stale(fresh, 60) is False


def test_is_stale_just_under_threshold():
    under = (datetime.now(timezone.utc) - timedelta(minutes=59)).isoformat()
    assert is_stale(under, 60) is False


def test_is_stale_invalid_timestamp():
    assert is_stale("garbage", 60) is True


def test_is_stale_naive_timestamp():
    naive = (
        (datetime.now(timezone.utc) - timedelta(minutes=5))
        .replace(tzinfo=None)
        .isoformat()
    )
    assert is_stale(naive, 60) is False


def test_last_sync_time_empty(tmp_path):
    mgr = SyncStateManager(tmp_path / "state.json")
    assert mgr.last_sync_time() is None


def test_last_sync_time_missing_file(tmp_path):
    mgr = SyncStateManager(tmp_path / "nonexistent.json")
    assert mgr.last_sync_time() is None


def test_last_sync_time_single_repo(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "repos": {
                    "abc123": {
                        "repo": "github.com/org/k",
                        "branch": "main",
                        "last_commit": "sha1",
                        "last_sync": "2026-07-24T10:00:00+00:00",
                        "file_hashes": {},
                    }
                }
            }
        )
    )
    mgr = SyncStateManager(state_file)
    assert mgr.last_sync_time() == "2026-07-24T10:00:00+00:00"


def test_last_sync_time_multiple_repos(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "repos": {
                    "a": {
                        "repo": "r1",
                        "branch": "main",
                        "last_commit": "s1",
                        "last_sync": "2026-07-24T08:00:00+00:00",
                        "file_hashes": {},
                    },
                    "b": {
                        "repo": "r2",
                        "branch": "main",
                        "last_commit": "s2",
                        "last_sync": "2026-07-24T12:00:00+00:00",
                        "file_hashes": {},
                    },
                }
            }
        )
    )
    mgr = SyncStateManager(state_file)
    assert mgr.last_sync_time() == "2026-07-24T12:00:00+00:00"
