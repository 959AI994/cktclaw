"""Shared agent-loop helpers for Web chat (tool schemas, execution, parsing)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from ..llm.types import ToolCall, ToolCallDelta
from ..tools.base import ToolContext
from ..utils.tool_call_parser import ToolCallParser

logger = logging.getLogger(__name__)


async def load_tool_schemas(disable_tools: bool = False) -> Tuple[List[dict], List[str]]:
    """Build OpenAI-style tool schemas from capability_registry."""
    if disable_tools:
        return [], []

    from ..capability_registry import get_capability_registry

    cap_reg = get_capability_registry()
    entries = await cap_reg.list_all(user_invocable_only=True)
    schemas: List[dict] = []
    names: List[str] = []
    for entry in entries:
        if entry.name.startswith("chip-"):
            continue
        schemas.append(entry.to_openai_schema())
        names.append(entry.name)
    return schemas, names


def make_tool_parser(tool_names: List[str]) -> ToolCallParser:
    return ToolCallParser(allowed_tools=tool_names or None)


def parse_text_tool_calls(text: str, parser: ToolCallParser) -> List[ToolCall]:
    """Extract tool calls from plain-text / DSML markup when native FC is absent."""
    if not text or not text.strip():
        return []

    parsed = parser.parse(text)
    if not parsed or parsed.get("type") != "tool_call":
        return []

    name = parsed.get("name") or ""
    args = parsed.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"args": args}

    return [
        ToolCall(
            id=str(parsed.get("tool_call_id") or "text_call_1"),
            name=name,
            arguments=args if isinstance(args, dict) else {"args": args},
        )
    ]


def accumulate_tool_call_delta(
    tc: ToolCallDelta,
    buffers: Dict[str, str],
    names: Dict[str, str],
) -> Optional[ToolCall]:
    """Buffer streaming tool_call deltas; return ToolCall when complete."""
    if not tc.id:
        return None

    if tc.id not in buffers:
        buffers[tc.id] = ""
    if tc.name:
        names[tc.id] = tc.name
    buffers[tc.id] += tc.arguments_delta or ""

    if not tc.is_complete:
        return None

    tc_name = names.get(tc.id, tc.name or "")
    tc_args = tc.arguments
    if not tc_args and buffers.get(tc.id):
        try:
            tc_args = json.loads(buffers[tc.id])
        except json.JSONDecodeError:
            tc_args = {"args": buffers[tc.id]}

    return ToolCall(id=tc.id, name=tc_name, arguments=tc_args or {})


async def execute_tool_calls(
    tool_calls: List[ToolCall],
    *,
    session_id: str,
    working_dir: str,
) -> List[Tuple[ToolCall, str]]:
    """Execute tool calls via capability_registry; return (call, result_text) pairs."""
    from ..capability_registry import get_capability_registry

    cap_reg = get_capability_registry()
    ctx = ToolContext(session_id=session_id, working_dir=working_dir)

    async def _run_one(tc: ToolCall) -> Tuple[ToolCall, str]:
        try:
            result = await cap_reg.execute(tc.name, tc.arguments, ctx)
            if isinstance(result, str):
                return tc, result
            return tc, json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            logger.warning("Tool %s failed: %s", tc.name, e)
            return tc, f"Error: {e}"

    if len(tool_calls) == 1:
        return [await _run_one(tool_calls[0])]

    results = await asyncio.gather(*[_run_one(tc) for tc in tool_calls])
    return list(results)


def append_assistant_tool_round(
    messages: list,
    text: str,
    tool_calls: List[ToolCall],
    results: List[Tuple[ToolCall, str]],
) -> None:
    """Append assistant(tool_calls) + tool result messages for the next LLM turn."""
    from ..llm.base import ChatMessage
    from ..llm.types import MessageRole as LLMRole
    clean_text = ToolCallParser.strip_tool_markup(text)
    messages.append(
        ChatMessage(
            role=LLMRole.ASSISTANT,
            content=clean_text,
            tool_calls=tool_calls,
        )
    )
    for tc, result_text in results:
        messages.append(
            ChatMessage(
                role=LLMRole.TOOL,
                content=result_text,
                tool_call_id=tc.id,
                name=tc.name,
            )
        )
