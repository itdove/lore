"""Claude Code adapter compatibility module."""

from lore.hook_adapters.base_agent import BaseAgentAdapter

ClaudeAdapter = BaseAgentAdapter
ClaudeCodeAdapter = BaseAgentAdapter

__all__ = ["ClaudeAdapter", "ClaudeCodeAdapter", "BaseAgentAdapter"]
