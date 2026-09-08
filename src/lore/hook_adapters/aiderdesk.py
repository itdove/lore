"""AiderDesk hook adapter."""

from __future__ import annotations

from typing import Any, ClassVar

from lore.hook_adapters.kiro import KiroAdapter


class AiderDeskAdapter(KiroAdapter):
    """AiderDesk adapter; its extension uses the common normalized shape."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("aiderdesk", "aider_desk")

    @property
    def ide_type(self) -> str:
        return "aiderdesk"

    @property
    def name(self) -> str:
        return "AiderDesk"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        return "aiderdesk_version" in data or data.get("hook_source") == "aiderdesk"
