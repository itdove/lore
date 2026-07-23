from __future__ import annotations

import importlib.resources
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def _load_lore_instructions() -> str:
    lore_md = Path(".lore/LORE.md")
    if lore_md.exists():
        return lore_md.read_text()
    return importlib.resources.read_text("lore.mcp.skills", "LORE.md")


def create_server() -> FastMCP:
    return FastMCP("lore", instructions=_load_lore_instructions())
