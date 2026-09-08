"""OpenClaw hook adapter."""

from __future__ import annotations

from typing import Any, ClassVar

from lore.hook_adapters.kiro import KiroAdapter


class OpenClawAdapter(KiroAdapter):
    """OpenClaw adapter; its plugin uses the common normalized shape."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("openclaw", "open_claw")

    @property
    def ide_type(self) -> str:
        return "openclaw"

    @property
    def name(self) -> str:
        return "OpenClaw"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        return "openclaw_version" in data or data.get("hook_source") == "openclaw"
