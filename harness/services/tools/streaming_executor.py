"""
Streaming tool executor — chunk tool output for incremental UI updates.

Core features:
1. Stream tool execution
2. Real-time tool output
3. Support tool execution cancellation
"""

import asyncio
from typing import AsyncGenerator, Optional, Callable, Awaitable, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class StreamingToolUpdate:
    """Streaming tool update"""
    tool_call_id: str
    tool_name: str
    chunk: str
    is_complete: bool = False
    is_error: bool = False
    metadata: Optional[Dict[str, Any]] = None


class StreamingToolExecutor:
    """
    Streaming tool executor

    Supports streaming tool execution results
    """

    def __init__(
        self,
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]],
        chunk_size: int = 1024
    ):
        """
        Initialize streaming tool executor

        Args:
            tool_executor: Tool executor
            chunk_size: Chunk size per return (character count)
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
        Execute tool in streaming mode

        Args:
            tool_call_id: Tool call ID
            tool_name: Tool name
            tool_args: Tool arguments

        Yields:
            Streaming tool updates
        """
        try:
            # Execute tool
            result = await self.tool_executor(tool_name, tool_args)

            # Return result in chunks
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
            # Return error
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
        Execute tool call in streaming mode

        Args:
            tool_call: Tool call

        Yields:
            Streaming tool updates
        """
        # Extract tool information
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

        # Execute in streaming mode
        async for update in self.execute_streaming(tool_call_id, tool_name, tool_args):
            yield update

    def start_tool_execution(
        self,
        tool_call_id: str,
        tool_call: Dict[str, Any]
    ) -> asyncio.Task:
        """
        Start tool execution (background task)

        Args:
            tool_call_id: Tool call ID
            tool_call: Tool call

        Returns:
            Async task
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
        Wait for tool execution to complete

        Args:
            tool_call_id: Tool call ID

        Returns:
            Tool execution result
        """
        task = self.active_tasks.get(tool_call_id)
        if not task:
            return None

        try:
            result = await task
            return result
        finally:
            # Clean up task
            self.active_tasks.pop(tool_call_id, None)

    def cancel_tool(self, tool_call_id: str):
        """
        Cancel tool execution

        Args:
            tool_call_id: Tool call ID
        """
        task = self.active_tasks.get(tool_call_id)
        if task and not task.done():
            task.cancel()
            self.active_tasks.pop(tool_call_id, None)

    def cancel_all_tools(self):
        """Cancel all tool executions"""
        for tool_call_id in list(self.active_tasks.keys()):
            self.cancel_tool(tool_call_id)


async def collect_streaming_result(
    streaming_updates: AsyncGenerator[StreamingToolUpdate, None]
) -> str:
    """
    Collect streaming results

    Args:
        streaming_updates: Streaming update generator

    Returns:
        Complete result
    """
    chunks = []
    async for update in streaming_updates:
        chunks.append(update.chunk)
    return "".join(chunks)
