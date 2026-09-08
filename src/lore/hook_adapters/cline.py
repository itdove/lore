"""Cline and ZooCode hook adapter."""

from __future__ import annotations

from typing import Any, ClassVar

from lore.hook_adapters.base import HookAdapter, NormalizedHookInput


class ClineAdapter(HookAdapter):
    """Normalize Cline/ZooCode payloads."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("cline", "zoocode", "zoo_code")

    @property
    def ide_type(self) -> str:
        return "cline"

    @property
    def name(self) -> str:
        return "Cline / ZooCode"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        return "clineVersion" in data or "cline_version" in data

    def normalize(self, data: dict[str, Any]) -> NormalizedHookInput:
        return self._normalized(data)
