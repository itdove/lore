from __future__ import annotations

import asyncio

from lore.mcp.server import create_server

EXPECTED_TOOL_NAMES = {
    "query_knowledge",
    "list_knowledge",
    "list_conflicts",
    "health_check",
    "store_knowledge",
    "negate_knowledge",
    "delete_knowledge",
}


def test_mcp_v2_client_discovers_lore_tools(tmp_path, monkeypatch):
    """Exercise MCP 2.x tools/list request and response handling."""
    monkeypatch.chdir(tmp_path)
    from mcp import Client

    async def list_tools():
        async with Client(create_server()) as client:
            return await client.list_tools()

    result = asyncio.run(list_tools())

    assert {tool.name for tool in result.tools} == EXPECTED_TOOL_NAMES
    assert result.next_cursor is None
