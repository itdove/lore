from __future__ import annotations

import errno
import os
import time
from pathlib import Path

MAX_LOCK_AGE_SECONDS = 3600


class SyncLockManager:
    def __init__(self, lock_path: Path) -> None:
        self._path = lock_path

    def _read_lock(self) -> tuple[int | None, float | None]:
        try:
            lines = self._path.read_text(encoding="utf-8").strip().splitlines()
            pid = int(lines[0]) if lines else None
            ts = float(lines[1]) if len(lines) >= 2 else None
            return pid, ts
        except (FileNotFoundError, ValueError, OSError, IndexError):
            return None, None

    def _is_lock_stale(self) -> bool:
        pid, ts = self._read_lock()
        if pid is None:
            return True
        if ts is not None and time.monotonic() - ts > MAX_LOCK_AGE_SECONDS:
            return True
        try:
            os.kill(pid, 0)
            return False
        except OSError:
            return True

    def acquire(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n{time.monotonic()}".encode())
            os.close(fd)
            return True
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        if self._is_lock_stale():
            self._path.unlink(missing_ok=True)
            try:
                fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()}\n{time.monotonic()}".encode())
                os.close(fd)
                return True
            except OSError:
                return False
        return False

    def release(self) -> None:
        pid, _ = self._read_lock()
        if pid == os.getpid():
            self._path.unlink(missing_ok=True)

    @property
    def is_locked(self) -> bool:
        if not self._path.exists():
            return False
        return not self._is_lock_stale()

    def __enter__(self) -> SyncLockManager:
        if not self.acquire():
            raise RuntimeError("Sync already in progress (lock held).")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
        return None
