"""
Tool Orchestration Service - 工具编排服务

参考 Claude Code 的 toolOrchestration.ts 实现工具编排逻辑。

核心功能：
1. 并行执行只读工具
2. 串行执行写入工具
3. 工具执行结果管理
4. Context Modifier 机制
"""

import asyncio
from typing import List, Dict, Any, AsyncGenerator, Optional, Callable, Awaitable
from dataclasses import dataclass


@dataclass
class ToolExecutionResult:
    """工具执行结果"""
    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ContextModifier:
    """上下文修改器"""
    tool_use_id: str
    modify_context: Callable[[Any], Any]


@dataclass
class MessageUpdate:
    """消息更新"""
    message: Optional[Dict[str, Any]] = None
    new_context: Optional[Any] = None
    context_modifier: Optional[ContextModifier] = None


@dataclass
class ToolBatch:
    """工具批次"""
    is_concurrency_safe: bool
    tool_calls: List[Dict[str, Any]]


# 只读工具列表（可以并行执行）
READ_ONLY_TOOLS = {
    "Read",
    "Grep",
    "Glob",
    "WebFetch",
    "WebSearch",
    # EDA 只读工具
    "opensta",  # 静态时序分析（只读）
}

# 写入工具列表（必须串行执行）
WRITE_TOOLS = {
    "Write",
    "Edit",
    "Bash",
    # EDA 写入工具
    "abc",
    "yosys",
    "reverse",
}

# 最大并发数
MAX_TOOL_USE_CONCURRENCY = 10


def is_read_only_tool(tool_name: str) -> bool:
    """
    判断工具是否为只读工具

    Args:
        tool_name: 工具名称

    Returns:
        是否为只读工具
    """
    return tool_name in READ_ONLY_TOOLS


def partition_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[ToolBatch]:
    """
    将工具调用分区为批次

    规则：
    1. 连续的只读工具 → 一个并行批次
    2. 单个写入工具 → 一个串行批次

    Args:
        tool_calls: 工具调用列表

    Returns:
        工具批次列表
    """
    batches = []
    current_batch = []
    current_is_read_only = None

    for tool_call in tool_calls:
        # 提取工具名称
        if "function" in tool_call:
            tool_name = tool_call["function"]["name"]
        elif "name" in tool_call:
            tool_name = tool_call["name"]
        else:
            continue

        is_read_only = is_read_only_tool(tool_name)

        # 如果类型改变，创建新批次
        if current_is_read_only is not None and current_is_read_only != is_read_only:
            if current_batch:
                batches.append(ToolBatch(
                    is_concurrency_safe=current_is_read_only,
                    tool_calls=current_batch
                ))
                current_batch = []

        current_batch.append(tool_call)
        current_is_read_only = is_read_only

    # 添加最后一个批次
    if current_batch:
        batches.append(ToolBatch(
            is_concurrency_safe=current_is_read_only or False,
            tool_calls=current_batch
        ))

    return batches


async def execute_tool_call(
    tool_call: Dict[str, Any],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]]
) -> ToolExecutionResult:
    """
    执行单个工具调用

    Args:
        tool_call: 工具调用
        tool_executor: 工具执行器

    Returns:
        工具执行结果
    """
    # 提取工具信息
    if "function" in tool_call:
        # OpenAI 格式
        tool_name = tool_call["function"]["name"]
        tool_args = tool_call["function"].get("arguments", {})
        if isinstance(tool_args, str):
            import json
            tool_args = json.loads(tool_args)
        tool_call_id = tool_call.get("id", "")
    elif "name" in tool_call:
        # Anthropic 格式
        tool_name = tool_call["name"]
        tool_args = tool_call.get("input", {})
        tool_call_id = tool_call.get("id", "")
    else:
        return ToolExecutionResult(
            tool_call_id="",
            tool_name="unknown",
            content="Invalid tool call format",
            is_error=True
        )

    # 执行工具
    try:
        result = await tool_executor(tool_name, tool_args)
        return ToolExecutionResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            content=str(result),
            is_error=False
        )
    except Exception as e:
        return ToolExecutionResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            content=f"Error: {str(e)}",
            is_error=True
        )


async def run_tools_concurrently(
    tool_calls: List[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
    max_concurrency: int = MAX_TOOL_USE_CONCURRENCY
) -> List[ToolExecutionResult]:
    """
    并行执行工具

    Args:
        tool_calls: 工具调用列表
        tool_executor: 工具执行器
        max_concurrency: 最大并发数

    Returns:
        工具执行结果列表
    """
    # 创建信号量限制并发数
    semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_with_semaphore(tool_call):
        async with semaphore:
            return await execute_tool_call(tool_call, tool_executor)

    # 并行执行所有工具
    tasks = [execute_with_semaphore(tc) for tc in tool_calls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 过滤异常
    return [r for r in results if isinstance(r, ToolExecutionResult)]


async def run_tools_serially(
    tool_calls: List[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]]
) -> List[ToolExecutionResult]:
    """
    串行执行工具

    Args:
        tool_calls: 工具调用列表
        tool_executor: 工具执行器

    Returns:
        工具执行结果列表
    """
    results = []

    for tool_call in tool_calls:
        result = await execute_tool_call(tool_call, tool_executor)
        results.append(result)

    return results


async def run_tools(
    tool_calls: List[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
    context: Optional[Any] = None,
) -> AsyncGenerator[MessageUpdate, None]:
    """
    执行工具编排（完整实现，包含 Context Modifier）

    参考 toolOrchestration.ts:19-82

    自动将工具分批，并行执行只读工具，串行执行写入工具

    Args:
        tool_calls: 工具调用列表
        tool_executor: 工具执行器
        context: 工具使用上下文（可选）

    Yields:
        消息更新（包含 message, new_context, context_modifier）
    """
    current_context = context

    # 分区工具调用
    batches = partition_tool_calls(tool_calls)

    for batch in batches:
        if batch.is_concurrency_safe:
            # 并行执行只读工具
            queued_context_modifiers: Dict[str, List[Callable[[Any], Any]]] = {}

            async for update in run_tools_concurrently_with_modifiers(
                batch.tool_calls,
                tool_executor
            ):
                # 收集 context modifiers
                if update.context_modifier:
                    tool_id = update.context_modifier.tool_use_id
                    if tool_id not in queued_context_modifiers:
                        queued_context_modifiers[tool_id] = []
                    queued_context_modifiers[tool_id].append(
                        update.context_modifier.modify_context
                    )

                # 返回消息更新（但不立即应用 context）
                yield MessageUpdate(
                    message=update.message,
                    new_context=current_context,
                )

            # 并行执行完成后，批量应用所有 context modifiers
            for tool_call in batch.tool_calls:
                tool_id = tool_call.get("id", "")
                modifiers = queued_context_modifiers.get(tool_id, [])
                for modifier in modifiers:
                    if current_context is not None:
                        current_context = modifier(current_context)

            # 返回更新后的 context
            yield MessageUpdate(new_context=current_context)

        else:
            # 串行执行写入工具
            async for update in run_tools_serially_with_modifiers(
                batch.tool_calls,
                tool_executor
            ):
                # 立即应用 context modifier
                if update.context_modifier and current_context is not None:
                    current_context = update.context_modifier.modify_context(
                        current_context
                    )

                # 返回消息和更新后的 context
                yield MessageUpdate(
                    message=update.message,
                    new_context=current_context,
                )


async def run_tools_concurrently_with_modifiers(
    tool_calls: List[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
    max_concurrency: int = MAX_TOOL_USE_CONCURRENCY
) -> AsyncGenerator[MessageUpdate, None]:
    """
    并行执行工具（支持 Context Modifier）

    Args:
        tool_calls: 工具调用列表
        tool_executor: 工具执行器
        max_concurrency: 最大并发数

    Yields:
        消息更新（包含 context_modifier）
    """
    # 创建信号量限制并发数
    semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_with_semaphore(tool_call):
        async with semaphore:
            result = await execute_tool_call(tool_call, tool_executor)

            # 创建消息
            message = tool_result_to_message(result)

            # 创建 context modifier（如果需要）
            context_modifier = None
            if _should_modify_context(result):
                context_modifier = ContextModifier(
                    tool_use_id=result.tool_call_id,
                    modify_context=lambda ctx: _apply_tool_result_to_context(
                        ctx, result
                    )
                )

            return MessageUpdate(
                message=message,
                context_modifier=context_modifier,
            )

    # 并行执行所有工具
    tasks = [execute_with_semaphore(tc) for tc in tool_calls]

    # 使用 asyncio.as_completed 来逐个返回结果
    for coro in asyncio.as_completed(tasks):
        try:
            update = await coro
            yield update
        except Exception as e:
            # 错误处理
            pass


async def run_tools_serially_with_modifiers(
    tool_calls: List[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]]
) -> AsyncGenerator[MessageUpdate, None]:
    """
    串行执行工具（支持 Context Modifier）

    Args:
        tool_calls: 工具调用列表
        tool_executor: 工具执行器

    Yields:
        消息更新（包含 context_modifier）
    """
    for tool_call in tool_calls:
        result = await execute_tool_call(tool_call, tool_executor)

        # 创建消息
        message = tool_result_to_message(result)

        # 创建 context modifier（如果需要）
        context_modifier = None
        if _should_modify_context(result):
            context_modifier = ContextModifier(
                tool_use_id=result.tool_call_id,
                modify_context=lambda ctx: _apply_tool_result_to_context(
                    ctx, result
                )
            )

        yield MessageUpdate(
            message=message,
            context_modifier=context_modifier,
        )


def _should_modify_context(result: ToolExecutionResult) -> bool:
    """
    判断工具结果是否需要修改上下文

    Args:
        result: 工具执行结果

    Returns:
        是否需要修改上下文
    """
    # 例如：Read 工具需要更新文件缓存
    # Write/Edit 工具需要更新文件状态
    return result.tool_name in ["Read", "Write", "Edit", "Bash"]


def _apply_tool_result_to_context(context: Any, result: ToolExecutionResult) -> Any:
    """
    将工具结果应用到上下文

    Args:
        context: 当前上下文
        result: 工具执行结果

    Returns:
        更新后的上下文
    """
    # 这里是示例实现，实际应该根据具体的 context 类型来处理
    if context is None:
        return None

    # 例如：更新文件缓存
    if result.tool_name == "Read" and hasattr(context, "file_cache"):
        # context.file_cache[file_path] = content
        pass

    return context


def tool_result_to_message(result: ToolExecutionResult) -> Dict[str, Any]:
    """
    将工具执行结果转换为消息格式

    Args:
        result: 工具执行结果

    Returns:
        消息字典
    """
    message = {
        "role": "tool",
        "tool_call_id": result.tool_call_id,
        "name": result.tool_name,
        "content": result.content,
    }

    if result.is_error:
        message["is_error"] = True

    if result.metadata:
        message["metadata"] = result.metadata

    return message


async def execute_tools_and_collect_messages(
    tool_calls: List[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]]
) -> List[Dict[str, Any]]:
    """
    执行工具并收集消息

    Args:
        tool_calls: 工具调用列表
        tool_executor: 工具执行器

    Returns:
        工具结果消息列表
    """
    messages = []

    async for result in run_tools(tool_calls, tool_executor):
        message = tool_result_to_message(result)
        messages.append(message)

    return messages
