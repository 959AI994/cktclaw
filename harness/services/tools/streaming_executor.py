"""
Streaming Tool Executor - 流式工具执行器

参考 Claude Code 的 StreamingToolExecutor.ts 实现流式工具执行。

核心功能：
1. 流式执行工具
2. 实时返回工具输出
3. 支持工具执行取消
"""

import asyncio
from typing import AsyncGenerator, Optional, Callable, Awaitable, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class StreamingToolUpdate:
    """流式工具更新"""
    tool_call_id: str
    tool_name: str
    chunk: str
    is_complete: bool = False
    is_error: bool = False
    metadata: Optional[Dict[str, Any]] = None


class StreamingToolExecutor:
    """
    流式工具执行器

    支持流式返回工具执行结果
    """

    def __init__(
        self,
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
        chunk_size: int = 1024
    ):
        """
        初始化流式工具执行器

        Args:
            tool_executor: 工具执行器
            chunk_size: 每次返回的块大小（字符数）
        """
        self.tool_executor = tool_executor
        self.chunk_size = chunk_size
        self.active_tasks: Dict[str, asyncio.Task] = {}

    async def execute_streaming(
        self,
        tool_call_id: str,
        tool_name: str,
        tool_args: Dict[str, Any]
    ) -> AsyncGenerator[StreamingToolUpdate, None]:
        """
        流式执行工具

        Args:
            tool_call_id: 工具调用 ID
            tool_name: 工具名称
            tool_args: 工具参数

        Yields:
            流式工具更新
        """
        try:
            # 执行工具
            result = await self.tool_executor(tool_name, tool_args)

            # 分块返回结果
            result_str = str(result)
            for i in range(0, len(result_str), self.chunk_size):
                chunk = result_str[i:i + self.chunk_size]
                is_complete = (i + self.chunk_size) >= len(result_str)

                yield StreamingToolUpdate(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    chunk=chunk,
                    is_complete=is_complete,
                    is_error=False
                )

        except Exception as e:
            # 返回错误
            yield StreamingToolUpdate(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                chunk=f"Error: {str(e)}",
                is_complete=True,
                is_error=True
            )

    async def execute_tool_streaming(
        self,
        tool_call: Dict[str, Any]
    ) -> AsyncGenerator[StreamingToolUpdate, None]:
        """
        流式执行工具调用

        Args:
            tool_call: 工具调用

        Yields:
            流式工具更新
        """
        # 提取工具信息
        if "function" in tool_call:
            tool_name = tool_call["function"]["name"]
            tool_args = tool_call["function"].get("arguments", {})
            if isinstance(tool_args, str):
                import json
                tool_args = json.loads(tool_args)
            tool_call_id = tool_call.get("id", "")
        elif "name" in tool_call:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("input", {})
            tool_call_id = tool_call.get("id", "")
        else:
            yield StreamingToolUpdate(
                tool_call_id="",
                tool_name="unknown",
                chunk="Invalid tool call format",
                is_complete=True,
                is_error=True
            )
            return

        # 流式执行
        async for update in self.execute_streaming(tool_call_id, tool_name, tool_args):
            yield update

    def start_tool_execution(
        self,
        tool_call_id: str,
        tool_call: Dict[str, Any]
    ) -> asyncio.Task:
        """
        启动工具执行（后台任务）

        Args:
            tool_call_id: 工具调用 ID
            tool_call: 工具调用

        Returns:
            异步任务
        """
        async def execute_and_collect():
            chunks = []
            async for update in self.execute_tool_streaming(tool_call):
                chunks.append(update.chunk)
            return "".join(chunks)

        task = asyncio.create_task(execute_and_collect())
        self.active_tasks[tool_call_id] = task
        return task

    async def wait_for_tool(self, tool_call_id: str) -> Optional[str]:
        """
        等待工具执行完成

        Args:
            tool_call_id: 工具调用 ID

        Returns:
            工具执行结果
        """
        task = self.active_tasks.get(tool_call_id)
        if not task:
            return None

        try:
            result = await task
            return result
        finally:
            # 清理任务
            self.active_tasks.pop(tool_call_id, None)

    def cancel_tool(self, tool_call_id: str):
        """
        取消工具执行

        Args:
            tool_call_id: 工具调用 ID
        """
        task = self.active_tasks.get(tool_call_id)
        if task and not task.done():
            task.cancel()
            self.active_tasks.pop(tool_call_id, None)

    def cancel_all_tools(self):
        """取消所有工具执行"""
        for tool_call_id in list(self.active_tasks.keys()):
            self.cancel_tool(tool_call_id)


async def collect_streaming_result(
    streaming_updates: AsyncGenerator[StreamingToolUpdate, None]
) -> str:
    """
    收集流式结果

    Args:
        streaming_updates: 流式更新生成器

    Returns:
        完整结果
    """
    chunks = []
    async for update in streaming_updates:
        chunks.append(update.chunk)
    return "".join(chunks)
