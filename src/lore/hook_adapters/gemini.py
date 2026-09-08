"""Google Gemini CLI hook adapter."""

from __future__ import annotations

from typing import Any, ClassVar

from lore.hook_adapters.base import HookAdapter, HookEvent, NormalizedHookInput


class GeminiCLIAdapter(HookAdapter):
    """Normalize Gemini CLI's PascalCase event names."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("gemini", "gemini_cli")

    @property
    def ide_type(self) -> str:
        return "gemini"

    @property
    def name(self) -> str:
        return "Google Gemini CLI"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        if "gemini_version" in data:
            return True
        if "transcript_path" not in data and "transcriptPath" not in data:
            return False
        event = data.get("hook_event_name", "")
        if not isinstance(event, str):
            return True
        return event.casefold() not in {
            "userpromptsubmit",
            "pretooluse",
            "posttooluse",
            "sessionstart",
            "sessionend",
        }

    def normalize(self, data: dict[str, Any]) -> NormalizedHookInput:
        event = HookEvent.from_name(data.get("hook_event_name"))
        return self._normalized(data, event=event or HookEvent.PROMPT)


GeminiAdapter = GeminiCLIAdapter

__all__ = ["GeminiAdapter", "GeminiCLIAdapter"]
