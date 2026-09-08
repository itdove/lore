"""Junie adapter placeholder.

Junie is MCP-only, but keeping a known adapter makes the supported-agent
registry explicit and gives setup code a stable integration name.
"""

from __future__ import annotations

from typing import Any, ClassVar

from lore.hook_adapters.base import HookAdapter, HookEvent, NormalizedHookInput


class JunieAdapter(HookAdapter):
    """Known MCP-only agent with no hook payloads."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("junie",)

    @property
    def ide_type(self) -> str:
        return "junie"

    @property
    def name(self) -> str:
        return "Junie"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        return False

    def normalize(self, data: dict[str, Any]) -> NormalizedHookInput:
        return NormalizedHookInput(event=HookEvent.PROMPT, raw_data=data)
