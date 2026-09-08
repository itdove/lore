"""Multi-agent hook adapter registry.

The registry keeps agent detection separate from Lore's lifecycle handlers:
the first adapter that recognizes a payload normalizes it into
NormalizedHookInput, and the handlers then apply the same recall, nudge, and
capture behavior to every agent.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from lore.hook_adapters.aiderdesk import AiderDeskAdapter
from lore.hook_adapters.augment import AugmentAdapter
from lore.hook_adapters.base import (
    ALL_HOOK_EVENT_DISPLAY_NAMES,
    HookAdapter,
    HookEvent,
    NormalizedHookInput,
)
from lore.hook_adapters.base_agent import BaseAgentAdapter
from lore.hook_adapters.claude import ClaudeAdapter, ClaudeCodeAdapter
from lore.hook_adapters.cline import ClineAdapter
from lore.hook_adapters.codex import CodexAdapter
from lore.hook_adapters.copilot import CopilotAdapter
from lore.hook_adapters.cursor import CURSOR_HOOK_EVENTS, CursorAdapter
from lore.hook_adapters.gemini import GeminiAdapter, GeminiCLIAdapter
from lore.hook_adapters.junie import JunieAdapter
from lore.hook_adapters.kiro import KiroAdapter
from lore.hook_adapters.openclaw import OpenClawAdapter
from lore.hook_adapters.opencode import OpenCodeAdapter
from lore.hook_adapters.windsurf import WindsurfAdapter

logger = logging.getLogger(__name__)

# The base adapter is Claude Code. More distinctive payloads must be checked
# first so, for example, Gemini's transcript_path is not mistaken for Claude.
ADAPTER_CLASSES = [
    ClineAdapter,
    GeminiCLIAdapter,
    WindsurfAdapter,
    CopilotAdapter,
    CursorAdapter,
    KiroAdapter,
    AiderDeskAdapter,
    OpenClawAdapter,
    AugmentAdapter,
    OpenCodeAdapter,
    CodexAdapter,
    JunieAdapter,
    BaseAgentAdapter,
]

SUPPORTED_IDES = (
    "claude",
    "cursor",
    "copilot",
    "codex",
    "windsurf",
    "gemini",
    "cline",
    "zoocode",
    "kiro",
    "augment",
    "opencode",
    "aiderdesk",
    "openclaw",
    "junie",
)

_ALIASES = {
    "claude-code": "claude",
    "github-copilot": "copilot",
    "github_copilot": "copilot",
    "gemini-cli": "gemini",
    "gemini_cli": "gemini",
    "open-ai-codex": "codex",
    "zoo-code": "zoocode",
    "cline-zoocode": "cline",
    "aider-desk": "aiderdesk",
    "open-claw": "openclaw",
    "augment-code": "augment",
    "open-code": "opencode",
}

_ENV_ALIAS_MAP: dict[str, type[HookAdapter]] = {}
for _adapter_class in ADAPTER_CLASSES:
    for _alias in _adapter_class.ENV_ALIASES:
        _ENV_ALIAS_MAP[_alias] = _adapter_class
for _alias, _canonical in _ALIASES.items():
    if _canonical in _ENV_ALIAS_MAP:
        _ENV_ALIAS_MAP[_alias] = _ENV_ALIAS_MAP[_canonical]


def _canonical_ide(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().casefold()
    return _ALIASES.get(normalized, normalized)


def detect_adapter(
    data: dict[str, Any] | None,
    ide_type: str | None = None,
) -> HookAdapter:
    """Select the adapter for a raw hook payload.

    Explicit agent selection takes precedence over environment overrides and
    auto-detection. This matters for Claude and Codex, whose payload formats
    intentionally overlap.
    """

    hook_data = data if isinstance(data, dict) else {}
    explicit = ide_type or hook_data.get("_ide_type") or hook_data.get("ide")
    explicit_key = _canonical_ide(explicit)
    if explicit_key in _ENV_ALIAS_MAP:
        return _ENV_ALIAS_MAP[explicit_key]()

    for env_name in ("LORE_IDE_TYPE", "LORE_AGENT", "AI_GUARDIAN_IDE_TYPE"):
        override = _canonical_ide(os.environ.get(env_name))
        if override in _ENV_ALIAS_MAP:
            return _ENV_ALIAS_MAP[override]()

    for adapter_class in ADAPTER_CLASSES:
        if adapter_class.can_handle(hook_data):
            return adapter_class()
    return BaseAgentAdapter()


def get_adapter_by_ide_type(ide_type: str | None) -> HookAdapter:
    """Return an adapter by its CLI/configuration name."""

    key = _canonical_ide(ide_type)
    adapter_class = _ENV_ALIAS_MAP.get(key, BaseAgentAdapter)
    return adapter_class()


def get_adapter(ide_type: str | None) -> HookAdapter:
    """Short alias for get_adapter_by_ide_type."""

    return get_adapter_by_ide_type(ide_type)


def normalize_hook(
    data: dict[str, Any],
    ide_type: str | None = None,
) -> NormalizedHookInput:
    """Detect and normalize one raw hook payload."""

    adapter = detect_adapter(data, ide_type=ide_type)
    return adapter.normalize(data)


__all__ = [
    "HookAdapter",
    "HookEvent",
    "NormalizedHookInput",
    "ALL_HOOK_EVENT_DISPLAY_NAMES",
    "CURSOR_HOOK_EVENTS",
    "BaseAgentAdapter",
    "ClaudeAdapter",
    "ClaudeCodeAdapter",
    "AiderDeskAdapter",
    "AugmentAdapter",
    "ClineAdapter",
    "CodexAdapter",
    "CopilotAdapter",
    "CursorAdapter",
    "GeminiCLIAdapter",
    "GeminiAdapter",
    "JunieAdapter",
    "KiroAdapter",
    "OpenClawAdapter",
    "OpenCodeAdapter",
    "WindsurfAdapter",
    "ADAPTER_CLASSES",
    "SUPPORTED_IDES",
    "detect_adapter",
    "get_adapter",
    "get_adapter_by_ide_type",
    "normalize_hook",
]
