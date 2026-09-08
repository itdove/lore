"""Kiro hook adapter."""

from __future__ import annotations

from typing import Any, ClassVar

from lore.hook_adapters.base import HookAdapter, NormalizedHookInput


class KiroAdapter(HookAdapter):
    """Normalize Kiro's snake_case hook events."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("kiro",)

    @property
    def ide_type(self) -> str:
        return "kiro"

    @property
    def name(self) -> str:
        return "Kiro"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        return "kiro_hook_type" in data or "kiro_version" in data

    def normalize(self, data: dict[str, Any]) -> NormalizedHookInput:
        return self._normalized(data)
