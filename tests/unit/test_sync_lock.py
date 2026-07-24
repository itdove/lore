import os

from lore.sync.lock import SyncLockManager


def test_acquire_uncontested(tmp_path):
    lock = SyncLockManager(tmp_path / "sync.lock")
    assert lock.acquire() is True
    assert lock.is_locked is True


def test_acquire_already_held(tmp_path):
    lock_path = tmp_path / "sync.lock"
    lock_path.write_text(str(os.getpid()))
    lock = SyncLockManager(lock_path)
    assert lock.acquire() is False


def test_acquire_stale_lock(tmp_path):
    lock_path = tmp_path / "sync.lock"
    lock_path.write_text("999999999")
    lock = SyncLockManager(lock_path)
    assert lock.acquire() is True
    assert lock.is_locked is True


def test_release(tmp_path):
    lock = SyncLockManager(tmp_path / "sync.lock")
    lock.acquire()
    lock.release()
    assert lock.is_locked is False
    assert not (tmp_path / "sync.lock").exists()


def test_release_different_pid(tmp_path):
    lock_path = tmp_path / "sync.lock"
    lock_path.write_text("1")
    lock = SyncLockManager(lock_path)
    lock.release()
    assert lock_path.exists()


def test_is_locked_no_file(tmp_path):
    lock = SyncLockManager(tmp_path / "nonexistent.lock")
    assert lock.is_locked is False


def test_is_locked_corrupt_file(tmp_path):
    lock_path = tmp_path / "sync.lock"
    lock_path.write_text("not-a-pid")
    lock = SyncLockManager(lock_path)
    assert lock.is_locked is False
