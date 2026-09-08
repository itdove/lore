"""Augment Code hook adapter."""

from __future__ import annotations

from typing import Any, ClassVar

from lore.hook_adapters.base_agent import BaseAgentAdapter

_AUGMENT_TOOL_MAP = {
    "launch-process": "Bash",
    "str-replace-editor": "Edit",
    "save-file": "Write",
    "view": "Read",
    "remove-files": "Delete",
}


class AugmentAdapter(BaseAgentAdapter):
    """Normalize Augment Code's tool names to Lore's canonical names."""

    ENV_ALIASES: ClassVar[tuple[str, ...]] = ("augment", "augment_code")

    @property
    def ide_type(self) -> str:
        return "augment"

    @property
    def name(self) -> str:
        return "Augment Code"

    @classmethod
    def can_handle(cls, data: dict[str, Any]) -> bool:
        return "is_mcp_tool" in data and "tool_name" in data

    def get_tool_name_map(self) -> dict[str, str]:
        return dict(_AUGMENT_TOOL_MAP)

    def normalize(self, data: dict[str, Any]):
        normalized = super().normalize(data)
        normalized.tool_name = _AUGMENT_TOOL_MAP.get(
            normalized.tool_name, normalized.tool_name
        )
        return normalized
