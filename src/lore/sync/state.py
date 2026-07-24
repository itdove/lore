from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class RepoSyncState:
    repo: str
    branch: str
    last_commit: str
    last_sync: str
    file_hashes: dict[str, str] = field(default_factory=dict)


class SyncStateManager:
    def __init__(self, state_path: Path) -> None:
        self._path = state_path

    def load(self) -> dict[str, RepoSyncState]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        result = {}
        for key, val in data.get("repos", {}).items():
            result[key] = RepoSyncState(
                repo=val["repo"],
                branch=val["branch"],
                last_commit=val["last_commit"],
                last_sync=val["last_sync"],
                file_hashes=val.get("file_hashes", {}),
            )
        return result

    def save(self, states: dict[str, RepoSyncState]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"repos": {key: asdict(st) for key, st in states.items()}}
        self._path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
