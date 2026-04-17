"""
Enhanced query loop — multi-turn LLM, tools, compaction, and budget.

Provides:
1. LLM calls with retries
2. Tool execution (parallel where safe)
3. Streaming-oriented step yields
4. Token budget tracking
5. Backoff on transient failures
6. Auto-compaction when over threshold
7. Tool / tool_result pairing repair
"""

import asyncio
import json
import time
from typing import AsyncGenerator, Optional, Dict, Any, List, Callable, Awaitable
from datetime import datetime
from dataclasses import dataclass, field

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


@dataclass
class TokenBudget:
    """Soft cap on tokens and estimated cost for one session."""
    max_tokens: int = 500_000
    max_cost: float = 10.0
    used_tokens: int = 0
    used_cost: float = 0.0

    def check_budget(self) -> bool:
        """True if still under both caps."""
        return (self.used_tokens < self.max_tokens and
                self.used_cost < self.max_cost)

    def record_usage(self, tokens: int, cost: float):
        self.used_tokens += tokens
        self.used_cost += cost

    def get_remaining_tokens(self) -> int:
        return max(0, self.max_tokens - self.used_tokens)


@dataclass
class LoopState:
    """
    Internal mutable state for one run() invocation.

    Separate from QueryStateEnum (orchestration labels).
    """
    messages: List[Dict[str, Any]]
    turn_count: int = 1
    auto_compact_tracking: Optional[AutoCompactTracking] = None
    transition: Optional[ContinueReason] = None
    max_output_tokens_recovery_count: int = 0
    has_attempted_reactive_compact: bool = False
    tool_use_blocks: List[Dict[str, Any]] = field(default_factory=list)
    assistant_messages: List[Dict[str, Any]] = field(default_factory=list)
    called_tool_signatures: set = field(default_factory=set)


class EnhancedQueryLoop:
    """
    Extended loop: budget, compaction, pairing, parallel tools.
    """

    def __init__(
        self,
        llm_func: Callable[[List[Dict[str, Any]]], Awaitable[Dict[str, Any]]],
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
        config: QueryConfig,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Args:
            llm_func: async (messages) -> provider response dict
            tool_executor: async (tool_name, args) -> string result
            config: QueryConfig thresholds and flags
            initial_messages: optional seed (reserved)
        """
        self.llm_func = llm_func
        self.tool_executor = tool_executor
        self.config = config

        self.total_tokens = 0
        self.total_cost = 0.0
        self.tool_calls = 0
        self.compactions = 0

        self.budget = TokenBudget(
            max_tokens=getattr(config, 'token_budget', None) or 500_000,
            max_cost=getattr(config, 'max_budget_usd', None) or 10.0,
        )

        self.max_retries = 3
        self.retry_delay = 1.0

    async def run(
        self,
        messages: List[Dict[str, Any]]
    ) -> AsyncGenerator[QueryResult, None]:
        """
        Run until terminal or error.

        Args:
            messages: starting transcript

        Yields:
            QueryResult for each major phase
        """
        state = LoopState(messages=messages.copy())

        try:
            while True:
                # 1) Stop if policy says terminal (turn cap, etc.)
                terminal = self._check_terminal_conditions(state)
                if terminal:
                    yield QueryResult(
                        state=QueryStateEnum.TERMINAL,
                        terminal_reason=terminal,
                        messages=state.messages,
                        total_tokens=self.total_tokens,
                        total_cost=self.total_cost,
                        tool_calls=self.tool_calls,
                        compactions=self.compactions,
                    )
                    return

                # 2) Budget guard
                if not self.budget.check_budget():
                    yield QueryResult(
                        state=QueryStateEnum.TERMINAL,
                        terminal_reason=TerminalReason.BUDGET_EXCEEDED,
                        messages=state.messages,
                        total_tokens=self.total_tokens,
                        total_cost=self.total_cost,
                        tool_calls=self.tool_calls,
                        compactions=self.compactions,
                    )
                    return

                # 3) Optional auto-compact
                if self._should_auto_compact(state):
                    yield QueryResult(
                        state=QueryStateEnum.CONTINUING,
                        continue_reason=ContinueReason.AUTO_COMPACT,
                        messages=state.messages,
                        total_tokens=self.total_tokens,
                    )

                    await self._perform_auto_compact(state)
                    self.compactions += 1
                    continue

                # 4) Repair missing tool_result rows
                missing_tool_ids = validate_tool_result_pairing(state.messages)
                if missing_tool_ids:
                    error_results = create_missing_tool_results(
                        missing_tool_ids,
                        "Tool execution was interrupted",
                    )
                    state.messages.extend(error_results)

                # 5) LLM with retries
                llm_response = await self._call_llm_with_retry(state.messages)

                if llm_response is None:
                    yield QueryResult(
                        state=QueryStateEnum.TERMINAL,
                        terminal_reason=TerminalReason.ERROR,
                        error_message="LLM call failed",
                        messages=state.messages,
                        total_tokens=self.total_tokens,
                    )
                    return

                # 6) Normalize assistant message
                assistant_message = self._process_llm_response(llm_response)
                state.messages.append(assistant_message)
                state.assistant_messages.append(assistant_message)

                if "usage" in llm_response:
                    usage = llm_response["usage"]
                    tokens = usage.get("total_tokens", 0)
                    self.total_tokens += tokens
                    self.budget.record_usage(tokens, tokens * 0.000001)

                # 7) Tools?
                tool_calls = self._extract_tool_calls(assistant_message)

                if not tool_calls:
                    yield QueryResult(
                        state=QueryStateEnum.TERMINAL,
                        terminal_reason=TerminalReason.END_TURN,
                        final_response=assistant_message.get("content", ""),
                        messages=state.messages,
                        total_tokens=self.total_tokens,
                        total_cost=self.total_cost,
                        tool_calls=self.tool_calls,
                        compactions=self.compactions,
                    )
                    return

                # 8) Run tools (parallel gather) with deduplication
                yield QueryResult(
                    state=QueryStateEnum.CONTINUING,
                    continue_reason=ContinueReason.TOOL_USE,
                    current_tool_name=tool_calls[0].get("function", {}).get("name", ""),
                    messages=state.messages,
                    total_tokens=self.total_tokens,
                )

                # Filter out duplicate tool calls
                filtered_calls, skipped_calls = self._filter_duplicate_tools(tool_calls, state)

                if not filtered_calls and skipped_calls:
                    # All tools were duplicates, inject warning message
                    warning_msg = {
                        "role": "tool",
                        "tool_call_id": skipped_calls[0].get("id", "duplicate"),
                        "name": "system",
                        "content": (
                            "⚠️ 检测到重复工具调用。您已经调用过相同的工具和参数。"
                            "请直接总结之前的工具输出结果，不要重复调用。"
                        ),
                    }
                    state.messages.append(warning_msg)
                    state.turn_count += 1
                    continue

                tool_results = await self._execute_tools_parallel(filtered_calls)

                for result in tool_results:
                    state.messages.append(result)

                self.tool_calls += len(filtered_calls)

                # 9) Next turn
                state.turn_count += 1
                state.transition = ContinueReason.TOOL_USE

        except Exception as e:
            yield QueryResult(
                state=QueryStateEnum.TERMINAL,
                terminal_reason=TerminalReason.ERROR,
                error_message=str(e),
                messages=state.messages,
                total_tokens=self.total_tokens,
            )
            return

    def _check_terminal_conditions(self, state: LoopState) -> Optional[TerminalReason]:
        """Max turns and similar hard stops."""
        if self.config.max_turns is not None and state.turn_count > self.config.max_turns:
            return TerminalReason.MAX_TURNS

        if not self.budget.check_budget():
            return TerminalReason.BUDGET_EXCEEDED

        return None

    def _should_auto_compact(self, state: LoopState) -> bool:
        """True when estimated prompt size exceeds threshold."""
        if not self.config.auto_compact_enabled:
            return False

        estimated_tokens = self._estimate_tokens(state.messages)

        return estimated_tokens > self.config.auto_compact_threshold

    async def _perform_auto_compact(self, state: LoopState):
        """Tail-keep strategy: drop oldest non-boundary messages until under target."""
        target_tokens = self.config.target_tokens

        kept_messages = []
        current_tokens = 0

        for msg in reversed(state.messages):
            msg_tokens = self._estimate_tokens([msg])
            if current_tokens + msg_tokens > target_tokens:
                break
            kept_messages.insert(0, msg)
            current_tokens += msg_tokens

        boundary_message = {
            "role": "system",
            "content": f"━━━ COMPACT BOUNDARY ━━━\nPrevious conversation has been summarized.\nPre-compact tokens: {self.total_tokens}\nTimestamp: {datetime.now().isoformat()}",
        }

        state.messages = [boundary_message] + kept_messages

    async def _call_llm_with_retry(
        self,
        messages: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Call llm_func with linear backoff between failures."""
        for attempt in range(self.max_retries):
            try:
                response = await self.llm_func(messages)
                return response
            except Exception:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                return None

        return None

    def _process_llm_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure an assistant-shaped dict."""
        if isinstance(response, dict):
            if "role" in response:
                return response
            return {
                "role": "assistant",
                "content": response.get("content", str(response)),
            }
        return {
            "role": "assistant",
            "content": str(response),
        }

    def _extract_tool_calls(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Read tool_calls or Anthropic tool_use blocks."""
        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            content = message.get("content", "")
            if isinstance(content, list):
                tool_calls = [
                    block for block in content
                    if isinstance(block, dict) and block.get("type") == "tool_use"
                ]

        return tool_calls

    def _filter_duplicate_tools(
        self,
        tool_calls: List[Dict[str, Any]],
        state: LoopState
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Filter out duplicate tool calls based on (tool_name, args_hash).
        Returns (filtered_calls, skipped_calls).
        """
        import hashlib

        filtered = []
        skipped = []

        for tool_call in tool_calls:
            # Extract tool name and args
            if "function" in tool_call:
                tool_name = tool_call["function"]["name"]
                tool_args = tool_call["function"]["arguments"]
            elif "type" in tool_call and tool_call["type"] == "tool_use":
                tool_name = tool_call["name"]
                tool_args = json.dumps(tool_call.get("input", {}), sort_keys=True)
            else:
                filtered.append(tool_call)
                continue

            # Create signature: (tool_name, args_hash)
            args_hash = hashlib.md5(str(tool_args).encode()).hexdigest()[:8]
            signature = (tool_name, args_hash)

            if signature in state.called_tool_signatures:
                skipped.append(tool_call)
            else:
                state.called_tool_signatures.add(signature)
                filtered.append(tool_call)

        return filtered, skipped

    async def _execute_tools_parallel(
        self,
        tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Run all tools in one asyncio.gather (best-effort)."""
        tasks = []

        for tool_call in tool_calls:
            if "function" in tool_call:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])
                tool_call_id = tool_call.get("id", "")
            elif "type" in tool_call and tool_call["type"] == "tool_use":
                tool_name = tool_call["name"]
                tool_args = tool_call.get("input", {})
                tool_call_id = tool_call.get("id", "")
            else:
                continue

            task = self._execute_single_tool(tool_name, tool_args, tool_call_id)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        return [r for r in results if not isinstance(r, Exception)]

    async def _execute_single_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_call_id: str
    ) -> Dict[str, Any]:
        """Invoke one tool and wrap as tool message."""
        try:
            result = await self.tool_executor(tool_name, tool_args)

            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "content": str(result),
            }
        except Exception as e:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "content": f"Error: {str(e)}",
                "is_error": True,
            }

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Heuristic token estimate with conservative multiplier."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content) // 4
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "") or block.get("content", "")
                        total += len(str(text)) // 4

        return int(total * 4 / 3)
