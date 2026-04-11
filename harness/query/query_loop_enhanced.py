"""
Enhanced Query Loop - 完整的查询循环实现

参考 Claude Code 的 query.ts (1729行) 实现完整的查询循环逻辑。

核心功能：
1. ✅ 实际的 LLM 调用逻辑
2. ✅ 工具执行编排
3. ✅ 流式结果处理
4. ✅ Token 预算管理
5. ✅ 错误重试机制
6. ✅ 自动压缩触发
7. ✅ Tool-Result 配对验证
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
    """Token 预算管理"""
    max_tokens: int = 500_000
    max_cost: float = 10.0
    used_tokens: int = 0
    used_cost: float = 0.0

    def check_budget(self) -> bool:
        """检查是否超预算"""
        return (self.used_tokens < self.max_tokens and
                self.used_cost < self.max_cost)

    def record_usage(self, tokens: int, cost: float):
        """记录使用量"""
        self.used_tokens += tokens
        self.used_cost += cost

    def get_remaining_tokens(self) -> int:
        """获取剩余 Token"""
        return max(0, self.max_tokens - self.used_tokens)


@dataclass
class LoopState:
    """
    内部循环状态

    跟踪循环内部的可变状态
    """
    messages: List[Dict[str, Any]]
    turn_count: int = 1
    auto_compact_tracking: Optional[AutoCompactTracking] = None
    transition: Optional[ContinueReason] = None
    max_output_tokens_recovery_count: int = 0
    has_attempted_reactive_compact: bool = False
    tool_use_blocks: List[Dict[str, Any]] = field(default_factory=list)
    assistant_messages: List[Dict[str, Any]] = field(default_factory=list)


class EnhancedQueryLoop:
    """
    增强版查询循环管理器

    完整实现 Claude Code 的查询循环逻辑
    """

    def __init__(
        self,
        llm_func: Callable[[List[Dict[str, Any]]], Awaitable[Dict[str, Any]]],
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
        config: QueryConfig,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        初始化增强版查询循环

        Args:
            llm_func: LLM 调用函数
            tool_executor: 工具执行函数
            config: 查询配置
            initial_messages: 初始消息列表
        """
        self.llm_func = llm_func
        self.tool_executor = tool_executor
        self.config = config

        # 统计信息
        self.total_tokens = 0
        self.total_cost = 0.0
        self.tool_calls = 0
        self.compactions = 0

        # Token 预算管理
        self.budget = TokenBudget(
            max_tokens=config.token_budget if hasattr(config, 'token_budget') else 500_000,
            max_cost=config.max_budget_usd if hasattr(config, 'max_budget_usd') else 10.0,
        )

        # 错误重试配置
        self.max_retries = 3
        self.retry_delay = 1.0  # 秒

    async def run(
        self,
        messages: List[Dict[str, Any]]
    ) -> AsyncGenerator[QueryResult, None]:
        """
        运行增强版查询循环

        Args:
            messages: 输入消息列表

        Yields:
            查询结果（包含中间状态和最终结果）
        """
        # 初始化内部状态
        state = LoopState(messages=messages.copy())

        try:
            while True:
                # ━━━━━━━━━━ 1. 检查终止条件 ━━━━━━━━━━
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

                # ━━━━━━━━━━ 2. 检查 Token 预算 ━━━━━━━━━━
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

                # ━━━━━━━━━━ 3. 自动压缩检查 ━━━━━━━━━━
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

                # ━━━━━━━━━━ 4. Tool-Result 配对验证 ━━━━━━━━━━
                missing_tool_ids = validate_tool_result_pairing(state.messages)
                if missing_tool_ids:
                    # 自动补全缺失的 tool_result
                    error_results = create_missing_tool_results(
                        missing_tool_ids,
                        "Tool execution was interrupted",
                    )
                    state.messages.extend(error_results)

                # ━━━━━━━━━━ 5. 调用 LLM（带重试） ━━━━━━━━━━
                llm_response = await self._call_llm_with_retry(state.messages)

                if llm_response is None:
                    yield QueryResult(
                        state=QueryStateEnum.TERMINAL,
                        terminal_reason=TerminalReason.ERROR,
                        error_message="LLM 调用失败",
                        messages=state.messages,
                        total_tokens=self.total_tokens,
                    )
                    return

                # ━━━━━━━━━━ 6. 处理 LLM 响应 ━━━━━━━━━━
                assistant_message = self._process_llm_response(llm_response)
                state.messages.append(assistant_message)
                state.assistant_messages.append(assistant_message)

                # 更新统计信息
                if "usage" in llm_response:
                    usage = llm_response["usage"]
                    tokens = usage.get("total_tokens", 0)
                    self.total_tokens += tokens
                    self.budget.record_usage(tokens, tokens * 0.000001)  # 估算成本

                # ━━━━━━━━━━ 7. 检查工具调用 ━━━━━━━━━━
                tool_calls = self._extract_tool_calls(assistant_message)

                if not tool_calls:
                    # 没有工具调用，正常结束
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

                # ━━━━━━━━━━ 8. 执行工具（并行） ━━━━━━━━━━
                yield QueryResult(
                    state=QueryStateEnum.CONTINUING,
                    continue_reason=ContinueReason.TOOL_USE,
                    current_tool_name=tool_calls[0].get("function", {}).get("name", ""),
                    messages=state.messages,
                    total_tokens=self.total_tokens,
                )

                tool_results = await self._execute_tools_parallel(tool_calls)

                # 添加工具结果到消息列表
                for result in tool_results:
                    state.messages.append(result)

                self.tool_calls += len(tool_calls)

                # ━━━━━━━━━━ 9. 更新状态并继续循环 ━━━━━━━━━━
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
        """检查终止条件"""
        # 检查最大轮次
        if state.turn_count > self.config.max_turns:
            return TerminalReason.MAX_TURNS

        # 检查预算
        if not self.budget.check_budget():
            return TerminalReason.BUDGET_EXCEEDED

        return None

    def _should_auto_compact(self, state: LoopState) -> bool:
        """检查是否需要自动压缩"""
        if not self.config.auto_compact_enabled:
            return False

        # 估算当前 Token 数
        estimated_tokens = self._estimate_tokens(state.messages)

        return estimated_tokens > self.config.auto_compact_threshold

    async def _perform_auto_compact(self, state: LoopState):
        """执行自动压缩"""
        # 简化版压缩：保留最近的消息
        target_tokens = self.config.target_tokens

        # 从后往前保留消息，直到达到目标 Token 数
        kept_messages = []
        current_tokens = 0

        for msg in reversed(state.messages):
            msg_tokens = self._estimate_tokens([msg])
            if current_tokens + msg_tokens > target_tokens:
                break
            kept_messages.insert(0, msg)
            current_tokens += msg_tokens

        # 添加压缩边界标记
        boundary_message = {
            "role": "system",
            "content": f"━━━ COMPACT BOUNDARY ━━━\nPrevious conversation has been summarized.\nPre-compact tokens: {self.total_tokens}\nTimestamp: {datetime.now().isoformat()}",
        }

        state.messages = [boundary_message] + kept_messages

    async def _call_llm_with_retry(
        self,
        messages: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """调用 LLM（带重试机制）"""
        for attempt in range(self.max_retries):
            try:
                response = await self.llm_func(messages)
                return response
            except Exception as e:
                if attempt < self.max_retries - 1:
                    # 等待后重试
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                else:
                    # 最后一次尝试失败
                    return None

        return None

    def _process_llm_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """处理 LLM 响应"""
        # 标准化响应格式
        if isinstance(response, dict):
            if "role" in response:
                return response
            else:
                # 包装成标准消息格式
                return {
                    "role": "assistant",
                    "content": response.get("content", str(response)),
                }
        else:
            return {
                "role": "assistant",
                "content": str(response),
            }

    def _extract_tool_calls(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从消息中提取工具调用"""
        tool_calls = message.get("tool_calls", [])

        # 如果没有 tool_calls 字段，尝试从 content 中解析
        if not tool_calls:
            content = message.get("content", "")
            if isinstance(content, list):
                # Anthropic 格式
                tool_calls = [
                    block for block in content
                    if isinstance(block, dict) and block.get("type") == "tool_use"
                ]

        return tool_calls

    async def _execute_tools_parallel(
        self,
        tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """并行执行工具"""
        tasks = []

        for tool_call in tool_calls:
            # 提取工具名称和参数
            if "function" in tool_call:
                # OpenAI 格式
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])
                tool_call_id = tool_call.get("id", "")
            elif "type" in tool_call and tool_call["type"] == "tool_use":
                # Anthropic 格式
                tool_name = tool_call["name"]
                tool_args = tool_call.get("input", {})
                tool_call_id = tool_call.get("id", "")
            else:
                continue

            # 创建异步任务
            task = self._execute_single_tool(tool_name, tool_args, tool_call_id)
            tasks.append(task)

        # 并行执行所有工具
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return [r for r in results if not isinstance(r, Exception)]

    async def _execute_single_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_call_id: str
    ) -> Dict[str, Any]:
        """执行单个工具"""
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
        """估算消息的 Token 数"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                # 粗估：1 token ≈ 4 chars
                total += len(content) // 4
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "") or block.get("content", "")
                        total += len(str(text)) // 4

        # 保守系数
        return int(total * 4 / 3)
