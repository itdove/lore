"""Common hook adapter types and normalization helpers.

Agent integrations use different field names and event names for the same
session lifecycle. The adapters convert those payloads into the small,
agent-neutral representation consumed by Lore's hook handlers.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar


class HookEvent(str, Enum):
    """Canonical hook events understood by Lore."""

    PROMPT = "prompt"
    PRE_TOOL_USE = "pretooluse"
    POST_TOOL_USE = "posttooluse"
    BEFORE_READ_FILE = "beforereadfile"
    STOP = "stop"
    SESSION_START = "sessionstart"
    SESSION_END = "sessionend"
    POST_COMPACT = "postcompact"

    @property
    def display_name(self) -> str:
        """Return the PascalCase name used by Claude/Codex payloads."""

        return {
            HookEvent.SESSION_START: "SessionStart",
            HookEvent.PROMPT: "UserPromptSubmit",
            HookEvent.PRE_TOOL_USE: "PreToolUse",
            HookEvent.POST_TOOL_USE: "PostToolUse",
            HookEvent.BEFORE_READ_FILE: "PreToolUse",
            HookEvent.SESSION_END: "SessionEnd",
            HookEvent.STOP: "Stop",
            HookEvent.POST_COMPACT: "PostCompact",
        }[self]

    @classmethod
    def from_name(cls, name: str | None) -> HookEvent | None:
        """Map a known agent event name to a canonical event."""

        if not isinstance(name, str) or not name.strip():
            return None

        normalized = re.sub(r"[^a-z0-9]", "", name.casefold())
        mapping = {
            "prompt": cls.PROMPT,
            "userpromptsubmit": cls.PROMPT,
            "userpromptsubmitted": cls.PROMPT,
            "beforesubmitprompt": cls.PROMPT,
            "beforeagent": cls.PROMPT,
            "preuserprompt": cls.PROMPT,
            "promptsubmit": cls.PROMPT,
            "messagesubmit": cls.PROMPT,
            "pretooluse": cls.PRE_TOOL_USE,
            "beforetool": cls.PRE_TOOL_USE,
            "beforetooluse": cls.PRE_TOOL_USE,
            "beforeshellexecution": cls.PRE_TOOL_USE,
            "preruncommand": cls.PRE_TOOL_USE,
            "prewritecode": cls.PRE_TOOL_USE,
            "premcptooluse": cls.PRE_TOOL_USE,
            "pretool": cls.PRE_TOOL_USE,
            "posttooluse": cls.POST_TOOL_USE,
            "aftertool": cls.POST_TOOL_USE,
            "aftershellexecution": cls.POST_TOOL_USE,
            "postruncommand": cls.POST_TOOL_USE,
            "postreadcode": cls.POST_TOOL_USE,
            "postwritecode": cls.POST_TOOL_USE,
            "postmcptooluse": cls.POST_TOOL_USE,
            "agentstop": cls.POST_TOOL_USE,
            "toolexecutebefore": cls.PRE_TOOL_USE,
            "toolexecuteafter": cls.POST_TOOL_USE,
            "beforereadfile": cls.BEFORE_READ_FILE,
            "prereadcode": cls.BEFORE_READ_FILE,
            "sessionstart": cls.SESSION_START,
            "sessionend": cls.SESSION_END,
            "stop": cls.STOP,
            "postcompact": cls.POST_COMPACT,
        }
        return mapping.get(normalized)

    @classmethod
    def from_display_name(cls, name: str | None) -> HookEvent | None:
        """Return the event represented by a PascalCase protocol name."""

        if not isinstance(name, str):
            return None
        for event in cls:
            if event.display_name == name:
                return event
        return None


ALL_HOOK_EVENT_DISPLAY_NAMES = frozenset(event.display_name for event in HookEvent)


@dataclass
class NormalizedHookInput:
    """Agent-neutral representation of a hook payload."""

    event: HookEvent
    tool_name: str | None = None
    tool_input: dict[str, Any] = field(default_factory=dict)
    file_path: str | None = None
    working_dir: str | None = None
    session_id: str | None = None
    tool_use_id: str | None = None
    prompt_text: str | None = None
    tool_response: Any = None
    transcript_path: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


class HookAdapter(ABC):
    """Base contract for an agent-specific hook adapter.

    Concrete adapters only need to identify their payloads and normalize
    them. The normalize_input method is retained as a compatibility alias
    for the upstream ai-guardian naming.
    """

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ()

    @property
    def name(self) -> str:
        """Human-readable adapter name."""

        return self.__class__.__name__.removesuffix("Adapter")

    @classmethod
    @abstractmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        """Return whether this adapter recognizes data."""

    @abstractmethod
    def normalize(self, data: dict[str, Any]) -> NormalizedHookInput:
        """Normalize an agent-specific payload."""

    def normalize_input(self, data: dict[str, Any]) -> NormalizedHookInput:
        """Compatibility alias for callers using ai-guardian's API."""

        return self.normalize(data)

    @staticmethod
    def _extract_tool_name(data: dict[str, Any]) -> str | None:
        value = data.get("tool_name") or data.get("toolName")
        if isinstance(value, str) and value:
            return value

        for container_key in ("tool_use", "toolUse", "tool"):
            container = data.get(container_key)
            if isinstance(container, dict):
                value = container.get("name") or container.get("tool_name")
                if isinstance(value, str) and value:
                    return value
        return None

    @staticmethod
    def _parse_object(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value:
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @classmethod
    def _extract_tool_input(cls, data: dict[str, Any]) -> dict[str, Any]:
        for container_key in ("tool_use", "toolUse"):
            container = data.get(container_key)
            if isinstance(container, dict):
                for key in ("input", "parameters", "arguments"):
                    value = container.get(key)
                    if isinstance(value, dict):
                        return value

        for key in (
            "tool_input",
            "toolInput",
            "parameters",
            "arguments",
            "tool_args",
            "toolArgs",
        ):
            value = data.get(key)
            parsed = cls._parse_object(value)
            if parsed:
                return parsed

        tool = data.get("tool")
        if isinstance(tool, dict):
            for key in ("input", "parameters", "arguments"):
                parsed = cls._parse_object(tool.get(key))
                if parsed:
                    return parsed
        return {}

    @classmethod
    def _extract_file_path_from_tool_input(cls, data: dict[str, Any]) -> str | None:
        for key in ("file_path", "filePath", "path"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value

        tool_input = cls._extract_tool_input(data)
        for key in ("file_path", "filePath", "path"):
            value = tool_input.get(key)
            if isinstance(value, str) and value:
                return value

        for container_key in ("tool", "tool_use", "toolUse"):
            container = data.get(container_key)
            if isinstance(container, dict):
                for key in ("file_path", "filePath", "path"):
                    value = container.get(key)
                    if isinstance(value, str) and value:
                        return value
        return None

    @staticmethod
    def _extract_prompt_text(data: dict[str, Any]) -> str | None:
        for key in ("prompt", "message", "user_message", "userMessage", "text"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                content = value.get("content") or value.get("text")
                if isinstance(content, str) and content:
                    return content
        return None

    @staticmethod
    def _extract_transcript_path(data: dict[str, Any]) -> str | None:
        for key in (
            "transcript_path",
            "transcriptPath",
            "conversation_path",
            "conversationPath",
        ):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        transcript = data.get("transcript")
        if isinstance(transcript, str) and transcript.startswith(("/", "~")):
            return transcript
        return None

    @staticmethod
    def _extract_working_dir(data: dict[str, Any]) -> str | None:
        for key in ("cwd", "working_dir", "workingDir", "workspace"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _extract_session_id(data: dict[str, Any]) -> str | None:
        for key in (
            "session_id",
            "sessionId",
            "conversation_id",
            "conversationId",
            "trajectory_id",
            "thread_id",
        ):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _extract_tool_use_id(data: dict[str, Any]) -> str | None:
        for key in ("tool_use_id", "toolUseId", "tool_call_id", "toolCallId"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @classmethod
    def _extract_tool_response(cls, data: dict[str, Any]) -> Any:
        for key in ("tool_response", "toolResponse", "tool_output", "toolOutput"):
            if key in data:
                return data[key]
        return None

    @classmethod
    def _detect_event(cls, data: dict[str, Any]) -> HookEvent:
        for key in (
            "agent_action_name",
            "hook_event_name",
            "hookEventName",
            "hookName",
            "hook_name",
            "event",
            "type",
        ):
            event = HookEvent.from_name(data.get(key))
            if event is not None:
                return event

        if cls._extract_tool_response(data) is not None:
            return HookEvent.POST_TOOL_USE
        if any(
            key in data
            for key in (
                "tool_use",
                "toolUse",
                "tool_name",
                "toolName",
                "tool_input",
                "toolInput",
            )
        ):
            return HookEvent.PRE_TOOL_USE
        if any(
            key in data for key in ("prompt", "message", "user_message", "userMessage")
        ):
            return HookEvent.PROMPT
        return HookEvent.PROMPT

    @classmethod
    def _detect_event_from_all_formats(cls, data: dict[str, Any]) -> HookEvent:
        """Compatibility name used by ai-guardian's adapter helpers."""

        return cls._detect_event(data)

    @classmethod
    def _normalized(
        cls,
        data: dict[str, Any],
        *,
        event: HookEvent | None = None,
        tool_name: str | None = None,
        tool_input: dict[str, Any] | None = None,
        file_path: str | None = None,
        prompt_text: str | None = None,
        transcript_path: str | None = None,
    ) -> NormalizedHookInput:
        return NormalizedHookInput(
            event=event or cls._detect_event(data),
            tool_name=(
                tool_name if tool_name is not None else cls._extract_tool_name(data)
            ),
            tool_input=(
                tool_input if tool_input is not None else cls._extract_tool_input(data)
            ),
            file_path=(
                file_path
                if file_path is not None
                else cls._extract_file_path_from_tool_input(data)
            ),
            working_dir=cls._extract_working_dir(data),
            session_id=cls._extract_session_id(data),
            tool_use_id=cls._extract_tool_use_id(data),
            prompt_text=(
                prompt_text
                if prompt_text is not None
                else cls._extract_prompt_text(data)
            ),
            tool_response=cls._extract_tool_response(data),
            transcript_path=(
                transcript_path
                if transcript_path is not None
                else cls._extract_transcript_path(data)
            ),
            raw_data=data,
        )
