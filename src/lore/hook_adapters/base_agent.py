"""Adapter for Claude Code and other PascalCase hook protocols."""

from __future__ import annotations

from typing import Any, ClassVar

from lore.hook_adapters.base import (
    ALL_HOOK_EVENT_DISPLAY_NAMES,
    HookAdapter,
    NormalizedHookInput,
)


class BaseAgentAdapter(HookAdapter):
    """Default adapter used by Claude Code and compatible agents."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("claude",)

    @property
    def ide_type(self) -> str:
        return "claude"

    @property
    def name(self) -> str:
        return "Claude Code"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        event_name = data.get("hook_event_name") or data.get("hookEventName")
        return event_name in ALL_HOOK_EVENT_DISPLAY_NAMES

    def normalize(self, data: dict[str, Any]) -> NormalizedHookInput:
        return self._normalized(data)

    def get_tool_name_map(self) -> dict[str, str]:
        return {}

    def get_default_transcript_paths(self) -> list[str]:
        return []
