"""Register coordinator Agent/SendMessage/TaskStop tools."""

from __future__ import annotations

from typing import Optional

from ..registry import ToolRegistry, get_tool_registry
from .coordinator_tools import SendMessageTool, SpawnAgentTool, TaskStopTool


def register_coordinator_tools(registry: Optional[ToolRegistry] = None) -> int:
    reg = registry or get_tool_registry()
    count = 0
    for tool in (SpawnAgentTool(), SendMessageTool(), TaskStopTool()):
        reg.register(tool, source="builtin", overwrite=True)
        count += 1
    return count
