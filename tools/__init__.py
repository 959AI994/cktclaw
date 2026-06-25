"""
CktClaw Tool System — unified tool registry with typed base class.

All tools (EDA, system, agent) implement BaseTool for consistent
function calling across LLM providers.
"""

from .base import BaseTool, ToolContext, ToolResult
from .registry import ToolRegistry, get_tool_registry
from .schema import to_openai_tools, to_anthropic_tools
from .guardrails import ToolGuardrails, GuardrailViolation

__all__ = [
    "BaseTool",
    "ToolContext",
    "ToolResult",
    "ToolRegistry",
    "get_tool_registry",
    "to_openai_tools",
    "to_anthropic_tools",
    "ToolGuardrails",
    "GuardrailViolation",
]
