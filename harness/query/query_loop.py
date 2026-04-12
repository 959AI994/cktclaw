"""
Query loop — multi-turn LLM + tool execution.

Responsibilities:
1. Manage the query loop lifecycle
2. Tool–result pairing validation
3. Auto-compaction triggers
4. Error recovery
5. Budget management

Design:
- Generator-style yields for intermediate states
- State machine (continue vs terminal)
- Immutable-style state snapshots per iteration
- Self-heal by synthesizing missing tool_result entries
"""

import asyncio
import json
from typing import AsyncGenerator, Optional, Dict, Any, List, Callable, Awaitable
from datetime import datetime

from .query_types import (
    QueryStateEnum,
    QueryConfig,
    QueryResult,
    TransitionType,
    ContinueReason,
    TerminalReason,
    AutoCompactTracking,
    validate_tool_result_pairing,
    create_missing_tool_results,
)


class LoopState:
    """
    Mutable per-loop state (distinct from QueryStateEnum).

    Tracks counters and messages while the loop runs.
    """
    def __init__(self, messages: List[Dict[str, Any]]):
        self.messages = messages
        self.turn_count = 1
        self.auto_compact_tracking: Optional[AutoCompactTracking] = None
        self.transition: Optional[ContinueReason] = None


class QueryLoop:
    """
    Query loop manager.

    Coordinates one full query: LLM calls and tool execution.
    """

    def __init__(
        self,
        llm_func: Callable[[List[Dict[str, Any]]], Awaitable[Dict[str, Any]]],
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
        config: QueryConfig,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Initialize the query loop.

        Args:
            llm_func: Async callable(messages) -> LLM response dict
            tool_executor: Async callable(tool_name, args) -> result string
            config: Query configuration
            initial_messages: Optional seed messages (reserved)
        """
        self.llm_func = llm_func
        self.tool_executor = tool_executor
        self.config = config
        self.total_tokens = 0
        self.total_cost = 0.0
        self.tool_calls = 0
        self.compactions = 0

    async def run(self, messages: List[Dict[str, Any]]) -> AsyncGenerator[QueryResult, None]:
        """
        Run the query loop.

        Args:
            messages: Chat messages for the API

        Yields:
            QueryResult for each significant step
        """
        # Initialize loop-local state
        state = LoopState(messages.copy())

        try:
            while True:
                # Terminal conditions (max turns, budget, etc.)
                terminal = self._check_terminal_conditions(state)
                if terminal:
                    yield QueryResult(
                        state=QueryStateEnum.TERMINAL,
                        terminal_reason=terminal,
                        messages=state.messages,
                        final_response=self._extract_final_response(state.messages),
                        total_turns=state.turn_count,
                        total_tokens=self.total_tokens,
                        total_cost=self.total_cost,
                        tool_calls=self.tool_calls,
                        compactions=self.compactions,
                    )
                    return

                # Auto-compact when over token threshold
                if self._should_auto_compact(state):
                    yield QueryResult(
                        state=QueryStateEnum.COMPACTING,
                        messages=state.messages,
                        total_turns=state.turn_count,
                    )
                    await self._perform_auto_compact(state)
                    self.compactions += 1

                # LLM call
                yield QueryResult(
                    state=QueryStateEnum.LLM_CALLING,
                    messages=state.messages,
                    total_turns=state.turn_count,
                )

                try:
                    llm_response = await self.llm_func(state.messages)
                except Exception as e:
                    yield QueryResult(
                        state=QueryStateEnum.TERMINAL,
                        terminal_reason=TerminalReason.ERROR,
                        messages=state.messages,
                        error_message=f"LLM call failed: {e}",
                        total_turns=state.turn_count,
                    )
                    return

                # Append assistant message
                state.messages.append(llm_response)

                # Tool calls present?
                tool_calls = self._extract_tool_calls(llm_response)

                if not tool_calls:
                    # No tools — end turn
                    final_response = self._extract_text_content(llm_response)
                    yield QueryResult(
                        state=QueryStateEnum.TERMINAL,
                        terminal_reason=TerminalReason.END_TURN,
                        messages=state.messages,
                        final_response=final_response,
                        total_turns=state.turn_count,
                        total_tokens=self.total_tokens,
                        total_cost=self.total_cost,
                        tool_calls=self.tool_calls,
                        compactions=self.compactions,
                    )
                    return

                # Execute tools
                yield QueryResult(
                    state=QueryStateEnum.TOOL_EXECUTING,
                    messages=state.messages,
                    current_tool_name=tool_calls[0].get("function", {}).get("name"),
                    total_turns=state.turn_count,
                )

                # Run each tool and collect tool messages
                tool_results = []
                for tool_call in tool_calls:
                    tool_id = tool_call.get("id", "")
                    function = tool_call.get("function", {})
                    tool_name = function.get("name", "")
                    tool_args_str = function.get("arguments", "{}")

                    try:
                        tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                    except json.JSONDecodeError:
                        tool_args = {}

                    try:
                        result = await self.tool_executor(tool_name, tool_args)
                        self.tool_calls += 1
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": str(result),
                        })
                    except Exception as e:
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": f"Error executing tool: {e}",
                        })

                # Append tool results for the next model turn
                state.messages.extend(tool_results)

                # Next iteration
                state.turn_count += 1

                yield QueryResult(
                    state=QueryStateEnum.CONTINUING,
                    messages=state.messages,
                    total_turns=state.turn_count,
                )

        except Exception as e:
            yield QueryResult(
                state=QueryStateEnum.TERMINAL,
                terminal_reason=TerminalReason.ERROR,
                messages=state.messages,
                error_message=str(e),
                total_turns=state.turn_count,
                total_tokens=self.total_tokens,
                total_cost=self.total_cost,
                tool_calls=self.tool_calls,
                compactions=self.compactions,
            )
            return

    def _check_terminal_conditions(self, state: LoopState) -> Optional[TerminalReason]:
        """Return a terminal reason if the loop must stop."""
        if self.config.max_turns and state.turn_count > self.config.max_turns:
            return TerminalReason.MAX_TURNS

        if self.config.max_budget_usd and self.total_cost > self.config.max_budget_usd:
            return TerminalReason.BUDGET_EXCEEDED

        return None

    def _extract_tool_calls(self, llm_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract tool_calls from an assistant message.

        Args:
            llm_response: Raw assistant message dict

        Returns:
            OpenAI-style tool_calls list (possibly normalized from Anthropic blocks)
        """
        tool_calls = llm_response.get("tool_calls", [])
        if tool_calls:
            return tool_calls

        # Legacy: tool_use blocks inside content[]
        content = llm_response.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    return [{
                        "id": block.get("id", "call_1"),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {})),
                        }
                    }]

        return []

    def _extract_text_content(self, llm_response: Dict[str, Any]) -> str:
        """
        Extract plain text from assistant content (string or block list).

        Args:
            llm_response: Assistant message dict

        Returns:
            Joined text for display or logging
        """
        content = llm_response.get("content", "")

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif "text" in block:
                        text_parts.append(block["text"])
            return "\n".join(text_parts)

        return str(content)

    def _extract_final_response(self, messages: List[Dict[str, Any]]) -> str:
        """
        Return user-visible text for terminal states (e.g. MAX_TURNS).

        If the last assistant turns are tool-call-only (empty content), walking
        backwards skips them; otherwise the UI shows「无响应」even though tools ran.
        """
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            text = self._extract_text_content(msg)
            if text and str(text).strip():
                return text
        # 仅有 tool_calls、无正文时：用最近若干条 tool 结果作为可读摘要
        tool_parts: List[str] = []
        for msg in reversed(messages):
            if msg.get("role") != "tool":
                continue
            c = msg.get("content", "")
            if c is not None and str(c).strip():
                tool_parts.append(str(c).strip())
            if len(tool_parts) >= 4:
                break
        if tool_parts:
            tool_parts.reverse()
            hdr = (
                "（本轮在达到最大对话轮次前未生成自然语言总结；"
                "以下为最近工具输出。）\n\n"
            )
            return hdr + "\n\n---\n\n".join(tool_parts)
        return ""

    def _should_auto_compact(self, state: LoopState) -> bool:
        """Whether estimated tokens exceed the auto-compact threshold."""
        if not self.config.auto_compact_enabled:
            return False

        estimated_tokens = self._estimate_tokens(state.messages)

        return estimated_tokens > self.config.auto_compact_threshold

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Rough token estimate (~4 chars per token)."""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "") or block.get("content", "")
                        total_chars += len(str(text))

        return total_chars // 4

    async def _perform_auto_compact(self, state: LoopState) -> None:
        """Drop older non-system messages to fit a smaller window."""
        system_messages = [msg for msg in state.messages if msg.get("role") == "system"]
        recent_messages = [msg for msg in state.messages if msg.get("role") != "system"]

        if len(recent_messages) > 10:
            # Keep a tail of recent messages; cap derived from target_tokens
            target_count = self.config.target_tokens // 1000
            target_count = max(5, min(target_count, len(recent_messages) // 2))
            recent_messages = recent_messages[-target_count:]

        state.messages = system_messages + recent_messages

        if not state.auto_compact_tracking:
            state.auto_compact_tracking = AutoCompactTracking()


def create_query_loop(
    llm_func: Callable[[List[Dict[str, Any]]], Awaitable[Dict[str, Any]]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
    config: QueryConfig,
    initial_messages: Optional[List[Dict[str, Any]]] = None,
) -> QueryLoop:
    """Factory for QueryLoop."""
    return QueryLoop(llm_func, tool_executor, config, initial_messages)


async def run_query(
    llm_func: Callable[[List[Dict[str, Any]]], Awaitable[Dict[str, Any]]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
    config: QueryConfig,
    messages: List[Dict[str, Any]],
) -> QueryResult:
    """
    Convenience wrapper: run the loop and return the last QueryResult.

    Args:
        llm_func: LLM async callable
        tool_executor: Tool async callable
        config: Query configuration
        messages: Initial messages

    Returns:
        Final QueryResult (or an error terminal if nothing yielded)
    """
    loop = create_query_loop(llm_func, tool_executor, config)

    result = None
    async for partial_result in loop.run(messages):
        result = partial_result

    return result or QueryResult(
        state=QueryStateEnum.TERMINAL,
        terminal_reason=TerminalReason.ERROR,
        error_message="Query loop did not return a result",
    )
