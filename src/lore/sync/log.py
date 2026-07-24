from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SyncResult:
    timestamp: str = ""
    repos_synced: list[str] = field(default_factory=list)
    created: int = 0
    updated: int = 0
    deleted: int = 0
    promoted: int = 0
    conflicts: int = 0
    blocked: int = 0
    errors: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)


class SyncLogWriter:
    def __init__(self, log_path: Path) -> None:
        self._path = log_path

    def write(self, result: SyncResult) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        repos = ", ".join(result.repos_synced) or "none"
        lines = [
            f"## Sync {result.timestamp}",
            "",
            f"**Repos:** {repos}",
            (
                f"**Created:** {result.created} | "
                f"**Updated:** {result.updated} | "
                f"**Deleted:** {result.deleted} | "
                f"**Promoted:** {result.promoted} | "
                f"**Conflicts:** {result.conflicts} | "
                f"**Blocked:** {result.blocked}"
            ),
        ]

        if result.errors:
            lines.append("")
            lines.append("### Errors")
            for err in result.errors:
                lines.append(f"- {err}")

        if result.details:
            lines.append("")
            lines.append("### Details")
            for detail in result.details:
                lines.append(f"- {detail}")

        lines.append("")
        lines.append("---")
        lines.append("")

        with open(self._path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
