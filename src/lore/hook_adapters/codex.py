"""OpenAI Codex hook adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from lore.hook_adapters.base_agent import BaseAgentAdapter


class CodexAdapter(BaseAgentAdapter):
    """Codex uses the same payload shape as Claude Code."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("codex",)

    @property
    def ide_type(self) -> str:
        return "codex"

    @property
    def name(self) -> str:
        return "OpenAI Codex"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        return bool(data.get("codex_version") or data.get("codex"))

    def get_default_transcript_paths(self) -> list[str]:
        sessions_dir = Path.home() / ".codex" / "sessions"
        if not sessions_dir.is_dir():
            return []

        try:
            paths = list(sessions_dir.glob("**/*.jsonl"))
            paths.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        except OSError:
            return []
        return [str(path) for path in paths]
