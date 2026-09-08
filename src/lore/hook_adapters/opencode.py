"""OpenCode hook adapter."""

from __future__ import annotations

from typing import Any, ClassVar

from lore.hook_adapters.base_agent import BaseAgentAdapter


class OpenCodeAdapter(BaseAgentAdapter):
    """OpenCode plugin events share Lore's common payload protocol."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("opencode", "open_code")

    @property
    def ide_type(self) -> str:
        return "opencode"

    @property
    def name(self) -> str:
        return "OpenCode"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        return bool(
            data.get("opencode_version") or data.get("hook_source") == "opencode"
        )
