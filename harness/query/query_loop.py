"""
Query Loop - 查询循环实现

参考 src/query.ts 实现 Python 版本的查询循环。

核心职责：
1. 管理查询循环生命周期
2. Tool-Result 配对验证
3. 自动压缩触发
4. 错误恢复
5. 预算管理

设计原则：
- 生成器模式（yield 中间结果）
- 状态机驱动（Continue/Terminal）
- 不可变状态（每次迭代创建新状态）
- 错误自愈（自动补全缺失的 tool_result）
"""

import asyncio
from typing import AsyncGenerator, Optional, Dict, Any, List
from datetime import datetime

from .query_types import (
    QueryState,
    QueryConfig,
    QueryResult,
    TransitionType,
    ContinueReason,
    TerminalReason,
    AutoCompactTracking,
    validate_tool_result_pairing,
    create_missing_tool_results,
)


class QueryLoop:
    """
    查询循环管理器

    管理单次查询的完整生命周期
    """

    def __init__(
        self,
        config: QueryConfig,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
    ):
        self.config = config
        self.state = QueryState(
            messages=initial_messages or [],
            turn_count=1,
        )
        self.total_tokens = 0
        self.total_cost = 0.0
        self.tool_calls = 0
        self.compactions = 0

    async def run(self):
        """
        运行查询循环

        Yields:
            中间事件（消息、工具调用等）或最终查询结果
        """
        try:
            while True:
                # 检查终止条件
                terminal = self._check_terminal_conditions()
                if terminal:
                    yield QueryResult(
                        terminal_reason=terminal,
                        messages=self.state.messages,
                        total_turns=self.state.turn_count,
                        total_tokens=self.total_tokens,
                        total_cost=self.total_cost,
                        tool_calls=self.tool_calls,
                        compactions=self.compactions,
                    )
                    return

                # 验证 Tool-Result 配对
                missing_ids = validate_tool_result_pairing(self.state.messages)
                if missing_ids:
                    # 自动补全缺失的 tool_result
                    error_results = create_missing_tool_results(
                        missing_ids,
                        "Tool execution was interrupted",
                    )
                    self.state.messages.extend(error_results)
                    yield {
                        "type": "tool_result_healing",
                        "missing_ids": missing_ids,
                        "healed": True,
                    }

                # 检查是否需要自动压缩
                if self._should_auto_compact():
                    yield {"type": "auto_compact_triggered"}
                    await self._perform_auto_compact()
                    self.compactions += 1

                # 模拟 API 调用（实际实现中会调用 LLM）
                yield {"type": "api_request_start", "turn": self.state.turn_count}

                # 检查是否需要继续
                continue_reason = self._check_continue_conditions()
                if continue_reason:
                    self.state.transition = continue_reason
                    self.state.turn_count += 1
                    yield {"type": "continue", "reason": continue_reason.value}
                    continue

                # 正常结束
                yield QueryResult(
                    terminal_reason=TerminalReason.END_TURN,
                    messages=self.state.messages,
                    total_turns=self.state.turn_count,
                    total_tokens=self.total_tokens,
                    total_cost=self.total_cost,
                    tool_calls=self.tool_calls,
                    compactions=self.compactions,
                )
                return

        except Exception as e:
            yield QueryResult(
                terminal_reason=TerminalReason.ERROR,
                messages=self.state.messages,
                total_turns=self.state.turn_count,
                total_tokens=self.total_tokens,
                total_cost=self.total_cost,
                tool_calls=self.tool_calls,
                compactions=self.compactions,
                error=str(e),
            )
            return

    def _check_terminal_conditions(self) -> Optional[TerminalReason]:
        """检查终止条件"""
        # 检查最大轮次
        if self.config.max_turns and self.state.turn_count > self.config.max_turns:
            return TerminalReason.MAX_TURNS

        # 检查预算
        if self.config.max_budget_usd and self.total_cost > self.config.max_budget_usd:
            return TerminalReason.BUDGET_EXCEEDED

        return None

    def _check_continue_conditions(self) -> Optional[ContinueReason]:
        """检查是否需要继续"""
        # 检查是否有未完成的工具调用
        if self._has_pending_tool_calls():
            return ContinueReason.TOOL_USE

        # 检查是否需要预算继续
        if self._should_budget_continue():
            return ContinueReason.BUDGET_CONTINUATION

        return None

    def _has_pending_tool_calls(self) -> bool:
        """检查是否有未完成的工具调用"""
        missing_ids = validate_tool_result_pairing(self.state.messages)
        return len(missing_ids) > 0

    def _should_budget_continue(self) -> bool:
        """检查是否应该预算继续"""
        if not self.config.token_budget:
            return False

        # 如果还有剩余预算，继续
        return self.total_tokens < self.config.token_budget

    def _should_auto_compact(self) -> bool:
        """检查是否应该自动压缩"""
        if not self.config.auto_compact_enabled:
            return False

        # 估算当前 Token 数
        estimated_tokens = self._estimate_tokens()

        return estimated_tokens > self.config.auto_compact_threshold

    def _estimate_tokens(self) -> int:
        """估算当前消息的 Token 数"""
        # 简单估算：每个字符约 0.25 token
        total_chars = 0
        for msg in self.state.messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "") or block.get("content", "")
                        total_chars += len(str(text))

        return total_chars // 4

    async def _perform_auto_compact(self) -> None:
        """执行自动压缩"""
        # 简化实现：保留最近的消息
        if len(self.state.messages) > 10:
            # 保留最近 5 条消息
            self.state.messages = self.state.messages[-5:]

            # 更新压缩跟踪
            if not self.state.auto_compact_tracking:
                self.state.auto_compact_tracking = AutoCompactTracking()

    def add_message(self, message: Dict[str, Any]) -> None:
        """添加消息"""
        self.state.messages.append(message)

    def update_usage(self, tokens: int, cost: float) -> None:
        """更新使用统计"""
        self.total_tokens += tokens
        self.total_cost += cost

    def increment_tool_calls(self) -> None:
        """增加工具调用计数"""
        self.tool_calls += 1


def create_query_loop(
    config: QueryConfig,
    initial_messages: Optional[List[Dict[str, Any]]] = None,
) -> QueryLoop:
    """创建查询循环"""
    return QueryLoop(config, initial_messages)


async def run_query(
    config: QueryConfig,
    initial_messages: Optional[List[Dict[str, Any]]] = None,
) -> QueryResult:
    """
    运行查询循环（便捷函数）

    Args:
        config: 查询配置
        initial_messages: 初始消息列表

    Returns:
        查询结果
    """
    loop = create_query_loop(config, initial_messages)

    result = None
    async for event in loop.run():
        # 处理中间事件（可以添加日志等）
        if isinstance(event, dict):
            event_type = event.get("type")
            if event_type == "auto_compact_triggered":
                pass  # 可以添加日志
            elif event_type == "tool_result_healing":
                pass  # 可以添加日志
        else:
            result = event

    return result or QueryResult(
        terminal_reason=TerminalReason.ERROR,
        error="Query loop did not return a result",
    )
