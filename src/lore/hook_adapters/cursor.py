"""Cursor hook adapter."""

from __future__ import annotations

from typing import Any, ClassVar

from lore.hook_adapters.base import HookAdapter, HookEvent, NormalizedHookInput

_CURSOR_EVENTS = {
    "beforeSubmitPrompt",
    "beforeReadFile",
    "beforeShellExecution",
    "afterShellExecution",
    "preToolUse",
    "postToolUse",
}
CURSOR_HOOK_EVENTS = tuple(_CURSOR_EVENTS)

__all__ = ["CursorAdapter", "CURSOR_HOOK_EVENTS"]


class CursorAdapter(HookAdapter):
    """Normalize Cursor's camelCase hook protocol."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("cursor",)

    @property
    def ide_type(self) -> str:
        return "cursor"

    @property
    def name(self) -> str:
        return "Cursor"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        if "cursor_version" in data or "cursorVersion" in data:
            return True
        if "hook_name" in data:
            return True
        event = data.get("hook_event_name")
        return isinstance(event, str) and event in _CURSOR_EVENTS

    @staticmethod
    def _extract_tool_name(data: dict[str, Any]) -> str | None:
        name = HookAdapter._extract_tool_name(data)
        if name:
            return name

        event = data.get("hook_event_name") or data.get("hook_name") or ""
        normalized = event.casefold() if isinstance(event, str) else ""
        if normalized == "beforereadfile":
            return "Read"
        if normalized in ("beforeshellexecution", "aftershellexecution"):
            return "Bash"
        return None

    @classmethod
    def _extract_tool_input(cls, data: dict[str, Any]) -> dict[str, Any]:
        result = super()._extract_tool_input(data)
        if result:
            return result
        command = data.get("command")
        return {"command": command} if isinstance(command, str) and command else {}

    def normalize(self, data: dict[str, Any]) -> NormalizedHookInput:
        event_name = data.get("hook_event_name") or data.get("hook_name")
        event = HookEvent.from_name(event_name) or HookEvent.PROMPT
        return self._normalized(
            data,
            event=event,
            tool_name=self._extract_tool_name(data),
            tool_input=self._extract_tool_input(data),
            file_path=data.get("file_path")
            or data.get("filePath")
            or self._extract_file_path_from_tool_input(data),
        )
