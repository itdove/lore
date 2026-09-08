"""Windsurf hook adapter."""

from __future__ import annotations

from typing import Any, ClassVar

from lore.hook_adapters.base import HookAdapter, HookEvent, NormalizedHookInput

_WINDSURF_EVENTS = {
    "pre_user_prompt": HookEvent.PROMPT,
    "pre_read_code": HookEvent.BEFORE_READ_FILE,
    "pre_run_command": HookEvent.PRE_TOOL_USE,
    "pre_write_code": HookEvent.PRE_TOOL_USE,
    "pre_mcp_tool_use": HookEvent.PRE_TOOL_USE,
    "post_run_command": HookEvent.POST_TOOL_USE,
    "post_read_code": HookEvent.POST_TOOL_USE,
    "post_write_code": HookEvent.POST_TOOL_USE,
    "post_mcp_tool_use": HookEvent.POST_TOOL_USE,
}


class WindsurfAdapter(HookAdapter):
    """Normalize Windsurf's agent_action_name payloads."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("windsurf",)

    @property
    def ide_type(self) -> str:
        return "windsurf"

    @property
    def name(self) -> str:
        return "Windsurf"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        return "agent_action_name" in data

    def normalize(self, data: dict[str, Any]) -> NormalizedHookInput:
        action = data.get("agent_action_name", "")
        event = (
            _WINDSURF_EVENTS.get(action.casefold(), HookEvent.PROMPT)
            if isinstance(action, str)
            else HookEvent.PROMPT
        )
        tool_info = data.get("tool_info")
        tool_name = self._extract_tool_name(data)
        if not tool_name and isinstance(tool_info, dict):
            tool_name = tool_info.get("name")
        tool_input = self._extract_tool_input(data)
        if not tool_input and isinstance(tool_info, dict):
            tool_input = tool_info
        return self._normalized(
            data,
            event=event,
            tool_name=tool_name,
            tool_input=tool_input,
        )
