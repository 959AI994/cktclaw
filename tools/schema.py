"""
Schema Converters — transform tool definitions between LLM provider formats.
"""

from typing import Any, Dict, List

from .base import BaseTool


def to_openai_tools(tools: List[BaseTool]) -> List[Dict[str, Any]]:
    """
    Convert a list of tools to OpenAI function calling format.

    Output format:
    [
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "...",
                "parameters": { JSON Schema }
            }
        }
    ]
    """
    return [tool.to_openai_schema() for tool in tools]


def to_anthropic_tools(tools: List[BaseTool]) -> List[Dict[str, Any]]:
    """
    Convert a list of tools to Anthropic tool_use format.

    Output format:
    [
        {
            "name": "tool_name",
            "description": "...",
            "input_schema": { JSON Schema }
        }
    ]
    """
    return [tool.to_anthropic_schema() for tool in tools]


def to_deepseek_tools(tools: List[BaseTool]) -> List[Dict[str, Any]]:
    """
    Convert to DeepSeek format (same as OpenAI).
    """
    return to_openai_tools(tools)


def openai_tool_call_to_params(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract tool name and parameters from an OpenAI-format tool call.

    Input: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "{...}"}}
    Output: {"tool_name": "...", "params": {...}, "call_id": "..."}
    """
    import json

    function = tool_call.get("function", {})
    name = function.get("name", "")
    arguments_str = function.get("arguments", "{}")

    try:
        params = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
    except json.JSONDecodeError:
        params = {}

    return {
        "tool_name": name,
        "params": params,
        "call_id": tool_call.get("id", ""),
    }


def anthropic_tool_call_to_params(content_block: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract tool name and parameters from an Anthropic content block.

    Input: {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
    Output: {"tool_name": "...", "params": {...}, "call_id": "..."}
    """
    return {
        "tool_name": content_block.get("name", ""),
        "params": content_block.get("input", {}),
        "call_id": content_block.get("id", ""),
    }
