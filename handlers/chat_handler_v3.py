"""
Chat Handler V3 - Streaming LLM + Native Function Calling

Uses the v2 LLM providers (cktclaw/llm/) for streaming output and native
function calling. Falls back to chat_handler_v2 for local models (Qwen/CodeV).

Improvements over V2:
1. Token-by-token streaming output via Rich Live
2. Native function calling (no text parsing) for DeepSeek/Claude/OpenAI
3. Uses unified ToolRegistry for tool schemas
4. Cleaner tool execution pipeline
"""

import time
import asyncio
import json
from typing import Optional, List, Dict, Any
from rich.console import Console

from ..ui import (
    render_error,
    render_user_message,
    render_completion_summary,
    Icons,
)


async def process_chat_v3(user_message: str, cli_state) -> None:
    """
    Handle chat with streaming + native function calling.

    Uses the new llm/ providers when available (deepseek/claude/openai),
    falls back to V2 handler for local models.

    Args:
        user_message: User's text input
        cli_state: Global CLI state (CLIState instance)
    """
    console = cli_state.console

    # Check if we should use the v2 LLM providers
    if not _should_use_v3(cli_state):
        # Fall back to V2 handler for local models
        from .chat_handler_v2 import process_chat_v2
        await process_chat_v2(user_message, cli_state)
        return

    # ━━━━━━━━━━ 1. Build context ━━━━━━━━━━
    try:
        messages = await cli_state.context_manager.build_context(
            session_id=cli_state.session_id,
            user_message=user_message,
            auto_compact=True,
        )
        messages_dict = [
            {
                "role": msg.role.value if hasattr(msg.role, 'value') else msg.role,
                "content": msg.content,
            }
            for msg in messages
        ]
    except Exception as e:
        render_error(console, f"Failed to build context: {e}", error_type="error")
        return

    # ━━━━━━━━━━ 2. Get LLM provider and tools ━━━━━━━━━━
    from ..llm import get_model_router
    from ..llm.base import ChatMessage
    from ..llm.types import MessageRole, ToolCall
    from ..tools import get_tool_registry
    from ..tools.base import ToolContext

    router = get_model_router()
    provider = router.current_provider
    if not provider:
        render_error(console, "No LLM provider configured", error_type="error")
        return

    registry = get_tool_registry()
    tool_schemas = registry.get_openai_tools()

    # Convert messages to ChatMessage format
    chat_messages = []
    for msg in messages_dict:
        role = msg.get("role", "user")
        role_enum = {
            "system": MessageRole.SYSTEM,
            "user": MessageRole.USER,
            "assistant": MessageRole.ASSISTANT,
            "tool": MessageRole.TOOL,
        }.get(role, MessageRole.USER)
        chat_messages.append(ChatMessage(role=role_enum, content=msg.get("content", "")))

    # ━━━━━━━━━━ 3. Streaming query loop ━━━━━━━━━━
    start_time = time.time()
    render_user_message(console, user_message)

    max_turns = 12
    final_text = ""

    for turn in range(max_turns):
        # Stream LLM response
        text_buffer = ""
        tool_calls: List[ToolCall] = []
        tool_call_buffers: Dict[str, str] = {}
        tool_call_names: Dict[str, str] = {}

        try:
            from rich.live import Live
            from rich.text import Text
            from rich.markdown import Markdown

            with Live(
                Text("", style="dim"),
                console=console,
                refresh_per_second=15,
                transient=True,
            ) as live:
                async for chunk in provider.chat_stream(
                    chat_messages,
                    tools=tool_schemas if tool_schemas else None,
                    temperature=0.3,
                    max_tokens=4096,
                ):
                    if chunk.text_delta:
                        text_buffer += chunk.text_delta
                        live.update(Text(text_buffer))

                    if chunk.tool_call_delta:
                        tc = chunk.tool_call_delta
                        if tc.id:
                            if tc.id not in tool_call_buffers:
                                tool_call_buffers[tc.id] = ""
                            if tc.name:
                                tool_call_names[tc.id] = tc.name
                            tool_call_buffers[tc.id] += tc.arguments_delta

                            if tc.is_complete:
                                tool_calls.append(ToolCall(
                                    id=tc.id,
                                    name=tool_call_names.get(tc.id, ""),
                                    arguments=tc.arguments,
                                ))

                    if chunk.is_done:
                        break

        except Exception as e:
            render_error(console, f"LLM stream error: {e}", error_type="error")
            return

        # Render streamed text as Markdown
        if text_buffer.strip():
            from rich.markdown import Markdown
            console.print(Markdown(text_buffer))

        if tool_calls:
            # ━━━━━━━━━━ Execute tool calls ━━━━━━━━━━
            chat_messages.append(ChatMessage(
                role=MessageRole.ASSISTANT,
                content=text_buffer,
                tool_calls=tool_calls,
            ))

            for tc in tool_calls:
                console.print(
                    f"  [dim]{Icons.CIRCUIT} Calling:[/dim] [bold cyan]{tc.name}[/bold cyan]"
                )

                tool = registry.get(tc.name)
                if tool:
                    ctx = ToolContext(
                        session_id=cli_state.session_id,
                        working_dir=getattr(cli_state, 'working_dir', ''),
                    )
                    try:
                        result = await tool.execute(tc.arguments, ctx)
                        result_content = result.output if result.success else f"Error: {result.error}"
                        status_icon = "[green]OK[/green]" if result.success else "[red]FAIL[/red]"
                    except Exception as e:
                        result_content = f"Tool execution error: {str(e)}"
                        status_icon = "[red]ERR[/red]"
                else:
                    # Try legacy skill execution
                    result_content = await _try_legacy_skill(tc.name, tc.arguments, cli_state)
                    status_icon = "[yellow]LEGACY[/yellow]"

                console.print(f"  [dim]  └─ {status_icon} ({len(result_content)} chars)[/dim]")

                chat_messages.append(ChatMessage(
                    role=MessageRole.TOOL,
                    content=result_content,
                    tool_call_id=tc.id,
                ))

            # Continue the loop for next LLM turn
            continue
        else:
            # No tool calls — this is the final response
            final_text = text_buffer
            break

    elapsed = time.time() - start_time

    # ━━━━━━━━━━ 4. Store in memory ━━━━━━━━━━
    try:
        from ..cktmem import MessageRole as CktMemRole, MessageType, ContextLayer

        await cli_state.storage.add_message(
            session_id=cli_state.session_id,
            role=CktMemRole.USER,
            content=user_message,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )
        await cli_state.storage.add_message(
            session_id=cli_state.session_id,
            role=CktMemRole.ASSISTANT,
            content=final_text,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )
    except Exception as e:
        console.print(f"[yellow]⚠️ Failed to store messages: {e}[/yellow]")

    # ━━━━━━━━━━ 5. Completion summary ━━━━━━━━━━
    render_completion_summary(
        console,
        timing_dict={"total": elapsed},
        title=f"Completed with {router.current_name}",
    )


def _should_use_v3(cli_state) -> bool:
    """Check if we should use V3 streaming handler."""
    try:
        from ..llm import get_model_router
        router = get_model_router()
        provider = router.current_provider
        if provider and provider.supports_streaming:
            return True
    except Exception:
        pass
    return False


async def _try_legacy_skill(tool_name: str, arguments: dict, cli_state) -> str:
    """Try to execute via the legacy SkillRegistry."""
    try:
        from ..harness import get_skill_registry

        skill_registry = get_skill_registry()
        skill = await skill_registry.get_skill(tool_name)
        if skill and skill.executor:
            context = {"cli_state": cli_state}
            args_str = arguments.get("args", json.dumps(arguments))
            result = await skill.executor(args_str, context)
            if isinstance(result, list):
                return "\n".join(
                    item.get("text", str(item))
                    for item in result
                    if isinstance(item, dict)
                )
            return str(result)
    except Exception as e:
        return f"Skill execution failed: {e}"

    return f"Unknown tool: {tool_name}"
