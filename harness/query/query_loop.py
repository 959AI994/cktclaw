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
    内部循环状态（与 QueryStateEnum 不同）

    用于跟踪循环内部的可变状态
    """
    def __init__(self, messages: List[Dict[str, Any]]):
        self.messages = messages
        self.turn_count = 1
        self.auto_compact_tracking: Optional[AutoCompactTracking] = None
        self.transition: Optional[ContinueReason] = None


class QueryLoop:
    """
    查询循环管理器

    管理单次查询的完整生命周期，协调 LLM 调用和工具执行
    """

    def __init__(
        self,
        llm_func: Callable[[List[Dict[str, Any]]], Awaitable[Dict[str, Any]]],
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
        config: QueryConfig,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        初始化查询循环

        Args:
            llm_func: LLM 调用函数，接收消息列表，返回 LLM 响应
            tool_executor: 工具执行函数，接收工具名和参数，返回执行结果
            config: 查询配置
            initial_messages: 初始消息列表
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
        运行查询循环

        Args:
            messages: 输入消息列表

        Yields:
            查询结果（包含中间状态和最终结果）
        """
        # 初始化内部状态
        state = LoopState(messages.copy())

        try:
            while True:
                # 检查终止条件
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

                # 检查是否需要自动压缩
                if self._should_auto_compact(state):
                    yield QueryResult(
                        state=QueryStateEnum.COMPACTING,
                        messages=state.messages,
                        total_turns=state.turn_count,
                    )
                    await self._perform_auto_compact(state)
                    self.compactions += 1

                # 调用 LLM
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

                # 添加 assistant 响应到消息列表
                state.messages.append(llm_response)

                # 检查是否有工具调用
                tool_calls = self._extract_tool_calls(llm_response)

                if not tool_calls:
                    # 没有工具调用，正常结束
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

                # 执行工具调用
                yield QueryResult(
                    state=QueryStateEnum.TOOL_EXECUTING,
                    messages=state.messages,
                    current_tool_name=tool_calls[0].get("function", {}).get("name"),
                    total_turns=state.turn_count,
                )

                # 执行所有工具并收集结果
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

                # 添加工具结果到消息列表
                state.messages.extend(tool_results)

                # 增加轮次计数
                state.turn_count += 1

                # 继续循环（LLM 会看到工具结果并生成下一个响应）
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
        """检查终止条件"""
        # 检查最大轮次
        if self.config.max_turns and state.turn_count > self.config.max_turns:
            return TerminalReason.MAX_TURNS

        # 检查预算
        if self.config.max_budget_usd and self.total_cost > self.config.max_budget_usd:
            return TerminalReason.BUDGET_EXCEEDED

        return None

    def _extract_tool_calls(self, llm_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从 LLM 响应中提取工具调用

        Args:
            llm_response: LLM 响应消息

        Returns:
            工具调用列表
        """
        tool_calls = llm_response.get("tool_calls", [])
        if tool_calls:
            return tool_calls

        # 兼容旧格式：检查 content 中是否有 tool_use
        content = llm_response.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    # 转换为标准格式
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
        从 LLM 响应中提取文本内容

        Args:
            llm_response: LLM 响应消息

        Returns:
            文本内容
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
        """从消息列表中提取最终响应"""
        # 找到最后一条 assistant 消息
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                return self._extract_text_content(msg)
        return ""

    def _should_auto_compact(self, state: LoopState) -> bool:
        """检查是否应该自动压缩"""
        if not self.config.auto_compact_enabled:
            return False

        # 估算当前 Token 数
        estimated_tokens = self._estimate_tokens(state.messages)

        return estimated_tokens > self.config.auto_compact_threshold

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算当前消息的 Token 数"""
        # 简单估算：每个字符约 0.25 token
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
        """执行自动压缩"""
        # 简化实现：保留系统消息和最近的消息
        system_messages = [msg for msg in state.messages if msg.get("role") == "system"]
        recent_messages = [msg for msg in state.messages if msg.get("role") != "system"]

        if len(recent_messages) > 10:
            # 保留最近 5 条消息
            target_count = self.config.target_tokens // 1000  # 粗略估算保留消息数
            target_count = max(5, min(target_count, len(recent_messages) // 2))
            recent_messages = recent_messages[-target_count:]

        state.messages = system_messages + recent_messages

        # 更新压缩跟踪
        if not state.auto_compact_tracking:
            state.auto_compact_tracking = AutoCompactTracking()


def create_query_loop(
    llm_func: Callable[[List[Dict[str, Any]]], Awaitable[Dict[str, Any]]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
    config: QueryConfig,
    initial_messages: Optional[List[Dict[str, Any]]] = None,
) -> QueryLoop:
    """创建查询循环"""
    return QueryLoop(llm_func, tool_executor, config, initial_messages)


async def run_query(
    llm_func: Callable[[List[Dict[str, Any]]], Awaitable[Dict[str, Any]]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
    config: QueryConfig,
    messages: List[Dict[str, Any]],
) -> QueryResult:
    """
    运行查询循环（便捷函数）

    Args:
        llm_func: LLM 调用函数
        tool_executor: 工具执行函数
        config: 查询配置
        messages: 输入消息列表

    Returns:
        查询结果
    """
    loop = create_query_loop(llm_func, tool_executor, config)

    result = None
    async for partial_result in loop.run(messages):
        result = partial_result

    return result or QueryResult(
        state=QueryState.TERMINAL,
        terminal_reason=TerminalReason.ERROR,
        error_message="Query loop did not return a result",
    )
