"""GitHub Copilot hook adapter."""

from __future__ import annotations

from typing import Any, ClassVar

from lore.hook_adapters.base import HookAdapter, HookEvent, NormalizedHookInput


class CopilotAdapter(HookAdapter):
    """Normalize GitHub Copilot's camelCase fields."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("copilot", "github_copilot")

    @property
    def ide_type(self) -> str:
        return "copilot"

    @property
    def name(self) -> str:
        return "GitHub Copilot"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        if "toolName" in data:
            return True
        event = data.get("hook_event_name")
        return bool(
            isinstance(event, str)
            and "timestamp" in data
            and "cwd" in data
            and event.casefold() in {"userpromptsubmitted", "pretooluse", "posttooluse"}
        )

    def normalize(self, data: dict[str, Any]) -> NormalizedHookInput:
        event_name = data.get("hook_event_name")
        event = HookEvent.from_name(event_name)
        if event is None:
            event = HookEvent.PRE_TOOL_USE if "toolName" in data else HookEvent.PROMPT

        tool_input = self._extract_tool_input(data)
        file_path = self._extract_file_path_from_tool_input(data)
        return self._normalized(
            data,
            event=event,
            tool_name=data.get("toolName") or data.get("tool_name"),
            tool_input=tool_input,
            file_path=file_path,
        )

    def get_default_transcript_paths(self) -> list[str]:
        from pathlib import Path

        path = Path.home() / ".copilot" / "session-state" / "events.jsonl"
        return [str(path)] if path.is_file() else []
