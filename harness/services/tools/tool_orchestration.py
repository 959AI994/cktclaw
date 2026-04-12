"""
Tool orchestration — batch read-only tools, serialize mutating tools.

Core features:
1. Parallel execution of read-only tools
2. Serial execution of write tools
3. Tool execution result management
4. Context Modifier mechanism
"""

import asyncio
from typing import List, Dict, Any, AsyncGenerator, Optional, Callable, Awaitable
from dataclasses import dataclass


@dataclass
class ToolExecutionResult:
    """Tool execution result"""
    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ContextModifier:
    """Context modifier"""
    tool_use_id: str
    modify_context: Callable[[Any], Any]


@dataclass
class MessageUpdate:
    """Message update"""
    message: Optional[Dict[str, Any]] = None
    new_context: Optional[Any] = None
    context_modifier: Optional[ContextModifier] = None


@dataclass
class ToolBatch:
    """Tool batch"""
    is_concurrency_safe: bool
    tool_calls: List[Dict[str, Any]]


# Read-only tools list (can be executed in parallel)
READ_ONLY_TOOLS = {
    "Read",
    "Grep",
    "Glob",
    "WebFetch",
    "WebSearch",
    # EDA read-only tools
    "opensta",  # Static timing analysis (read-only)
}

# Write tools list (must be executed serially)
WRITE_TOOLS = {
    "Write",
    "Edit",
    "Bash",
    # EDA write tools
    "abc",
    "yosys",
    "reverse",
}

# Maximum concurrency
MAX_TOOL_USE_CONCURRENCY = 10


def is_read_only_tool(tool_name: str) -> bool:
    """
    Determine if tool is read-only

    Args:
        tool_name: Tool name

    Returns:
        Whether it's read-only
    """
    return tool_name in READ_ONLY_TOOLS


def partition_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[ToolBatch]:
    """
    Partition tool calls into batches

    Rules:
    1. Consecutive read-only tools → one parallel batch
    2. Single write tool → one serial batch

    Args:
        tool_calls: Tool call list

    Returns:
        Tool batch list
    """
    batches = []
    current_batch = []
    current_is_read_only = None

    for tool_call in tool_calls:
        # Extract tool name
        if "function" in tool_call:
            tool_name = tool_call["function"]["name"]
        elif "name" in tool_call:
            tool_name = tool_call["name"]
        else:
            continue

        is_read_only = is_read_only_tool(tool_name)

        # If type changes, create new batch
        if current_is_read_only is not None and current_is_read_only != is_read_only:
            if current_batch:
                batches.append(ToolBatch(
                    is_concurrency_safe=current_is_read_only,
                    tool_calls=current_batch
                ))
                current_batch = []

        current_batch.append(tool_call)
        current_is_read_only = is_read_only

    # Add last batch
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
    Execute single tool call

    Args:
        tool_call: Tool call
        tool_executor: Tool executor

    Returns:
        Tool execution result
    """
    # Extract tool information
    if "function" in tool_call:
        # OpenAI format
        tool_name = tool_call["function"]["name"]
        tool_args = tool_call["function"].get("arguments", {})
        if isinstance(tool_args, str):
            import json
            tool_args = json.loads(tool_args)
        tool_call_id = tool_call.get("id", "")
    elif "name" in tool_call:
        # Anthropic format
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

    # Execute tool
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
    Execute tools in parallel

    Args:
        tool_calls: Tool call list
        tool_executor: Tool executor
        max_concurrency: Maximum concurrency

    Returns:
        Tool execution result list
    """
    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_with_semaphore(tool_call):
        async with semaphore:
            return await execute_tool_call(tool_call, tool_executor)

    # Execute all tools in parallel
    tasks = [execute_with_semaphore(tc) for tc in tool_calls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter exceptions
    return [r for r in results if isinstance(r, ToolExecutionResult)]


async def run_tools_serially(
    tool_calls: List[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]]
) -> List[ToolExecutionResult]:
    """
    Execute tools serially

    Args:
        tool_calls: Tool call list
        tool_executor: Tool executor

    Returns:
        Tool execution result list
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
    Execute tool calls with optional ContextModifier application.

    Read-only batches run concurrently; mutating batches run serially.

    Args:
        tool_calls: Tool call list
        tool_executor: Tool executor
        context: Tool use context (optional)

    Yields:
        Message updates (including message, new_context, context_modifier)
    """
    current_context = context

    # Partition tool calls
    batches = partition_tool_calls(tool_calls)

    for batch in batches:
        if batch.is_concurrency_safe:
            # Execute read-only tools in parallel
            queued_context_modifiers: Dict[str, List[Callable[[Any], Any]]] = {}

            async for update in run_tools_concurrently_with_modifiers(
                batch.tool_calls,
                tool_executor
            ):
                # Collect context modifiers
                if update.context_modifier:
                    tool_id = update.context_modifier.tool_use_id
                    if tool_id not in queued_context_modifiers:
                        queued_context_modifiers[tool_id] = []
                    queued_context_modifiers[tool_id].append(
                        update.context_modifier.modify_context
                    )

                # Return message update (but don't apply context immediately)
                yield MessageUpdate(
                    message=update.message,
                    new_context=current_context,
                )

            # After parallel execution completes, batch apply all context modifiers
            for tool_call in batch.tool_calls:
                tool_id = tool_call.get("id", "")
                modifiers = queued_context_modifiers.get(tool_id, [])
                for modifier in modifiers:
                    if current_context is not None:
                        current_context = modifier(current_context)

            # Return updated context
            yield MessageUpdate(new_context=current_context)

        else:
            # Execute write tools serially
            async for update in run_tools_serially_with_modifiers(
                batch.tool_calls,
                tool_executor
            ):
                # Apply context modifier immediately
                if update.context_modifier and current_context is not None:
                    current_context = update.context_modifier.modify_context(
                        current_context
                    )

                # Return message and updated context
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
    Execute tools in parallel (with Context Modifier support)

    Args:
        tool_calls: Tool call list
        tool_executor: Tool executor
        max_concurrency: Maximum concurrency

    Yields:
        Message updates (including context_modifier)
    """
    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_with_semaphore(tool_call):
        async with semaphore:
            result = await execute_tool_call(tool_call, tool_executor)

            # Create message
            message = tool_result_to_message(result)

            # Create context modifier (if needed)
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

    # Execute all tools in parallel
    tasks = [execute_with_semaphore(tc) for tc in tool_calls]

    # Use asyncio.as_completed to return results one by one
    for coro in asyncio.as_completed(tasks):
        try:
            update = await coro
            yield update
        except Exception as e:
            # Error handling
            pass


async def run_tools_serially_with_modifiers(
    tool_calls: List[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[str]]
) -> AsyncGenerator[MessageUpdate, None]:
    """
    Execute tools serially (with Context Modifier support)

    Args:
        tool_calls: Tool call list
        tool_executor: Tool executor

    Yields:
        Message updates (including context_modifier)
    """
    for tool_call in tool_calls:
        result = await execute_tool_call(tool_call, tool_executor)

        # Create message
        message = tool_result_to_message(result)

        # Create context modifier (if needed)
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
    Determine if tool result should modify context

    Args:
        result: Tool execution result

    Returns:
        Whether context should be modified
    """
    # Example: Read tool needs to update file cache
    # Write/Edit tools need to update file state
    return result.tool_name in ["Read", "Write", "Edit", "Bash"]


def _apply_tool_result_to_context(context: Any, result: ToolExecutionResult) -> Any:
    """
    Apply tool result to context

    Args:
        context: Current context
        result: Tool execution result

    Returns:
        Updated context
    """
    # This is example implementation, should be handled based on specific context type
    if context is None:
        return None

    # Example: update file cache
    if result.tool_name == "Read" and hasattr(context, "file_cache"):
        # context.file_cache[file_path] = content
        pass

    return context


def tool_result_to_message(result: ToolExecutionResult) -> Dict[str, Any]:
    """
    Convert tool execution result to message format

    Args:
        result: Tool execution result

    Returns:
        Message dictionary
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
    Run tools via run_tools and return a flat list of tool messages.

    Args:
        tool_calls: Provider tool call objects
        tool_executor: Callable invoked per tool

    Returns:
        List of tool-role message dicts
    """
    messages = []

    async for result in run_tools(tool_calls, tool_executor):
        message = tool_result_to_message(result)
        messages.append(message)

    return messages
