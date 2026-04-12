"""
Chat Handler V2 - QueryLoop Integration

重构版本的 chat_handler,使用 Harness QueryLoop 进行 Tool-Result 配对验证和错误自愈。

主要改进:
1. 使用 QueryLoop 替代原有的 agent loop
2. Tool-Result 配对验证
3. 自动错误自愈
4. 路由 tool_use 到 Skill 执行器
"""

import time
import asyncio
import json
from typing import Optional, List, Dict, Any
from rich.console import Console

from ..ui import (
    render_spinner,
    render_error,
    render_user_message,
    render_assistant_message,
    render_completion_summary,
    format_time,
    Icons,
)

from ..harness import (
    QueryConfig,
    QueryStateEnum,
    get_skill_registry,
)

from ..harness.services.api import (
    RateLimiter,
    RateLimitConfig,
)

try:
    from cktclaw.models import LLMVerilogAnalyzer
except ImportError as e:
    raise ImportError(f"Failed to import LLMVerilogAnalyzer: {e}")


# 全局速率限制器（单例模式）
_global_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """获取全局速率限制器"""
    global _global_rate_limiter

    if _global_rate_limiter is None:
        config = RateLimitConfig(
            max_requests_per_minute=60,  # 每分钟最多 60 个请求
            max_tokens_per_minute=100_000,  # 每分钟最多 100K tokens
        )
        _global_rate_limiter = RateLimiter(config)

    return _global_rate_limiter


async def process_chat_v2(user_message: str, cli_state) -> None:
    """
    Handle multi-turn chat message using QueryLoop.

    Workflow:
    1. Assemble context from cktmem
    2. Create QueryLoop with LLM wrapper
    3. Run QueryLoop (handles Tool-Result pairing automatically)
    4. Store messages in memory
    5. Render response

    Args:
        user_message: User's text input
        cli_state: Global CLI state (CLIState instance)
    """
    console = cli_state.console

    # ━━━━━━━━━━ 1. Assemble context (using cktmem) ━━━━━━━━━━
    try:
        messages = await cli_state.context_manager.build_context(
            session_id=cli_state.session_id,
            user_message=user_message,
            auto_compact=True,
        )

        # Convert cktmem Message objects to dict format
        messages_dict = [
            {
                "role": msg.role.value if hasattr(msg.role, 'value') else msg.role,
                "content": msg.content,
            }
            for msg in messages
        ]
    except Exception as e:
        render_error(
            console,
            f"Failed to build context: {e}",
            error_type="error",
        )
        return

    # ━━━━━━━━━━ 2. Initialize LLM analyzer ━━━━━━━━━━
    if cli_state.llm_analyzer is None:
        cli_state.llm_analyzer = LLMVerilogAnalyzer(verbose=False)

    # ━━━━━━━━━━ 3. Create QueryLoop ━━━━━━━━━━
    start_time = time.time()

    # Get system prompt from context manager
    system_prompt = cli_state.context_manager.system_prompt

    # Configure QueryLoop
    config = QueryConfig(
        system_prompt=system_prompt,
        max_turns=5,
        auto_compact_enabled=True,
        auto_compact_threshold=150_000,
        target_tokens=40_000,
    )

    # Create LLM wrapper function
    async def llm_wrapper(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Wrapper for LLM calls with rate limiting"""
        # 获取速率限制器
        limiter = get_rate_limiter()

        # 估算 Token 数
        estimated_tokens = sum(
            len(str(msg.get("content", ""))) // 4
            for msg in messages
        )

        # 速率限制检查
        can_proceed = await limiter.acquire(estimated_tokens=estimated_tokens)

        if not can_proceed:
            # 获取等待时间
            wait_time = limiter.get_wait_time()

            if cli_state.console:
                cli_state.console.print(
                    f"[yellow]⏳ Rate limit reached. Waiting {wait_time:.1f}s...[/yellow]"
                )

            # 等待
            await asyncio.sleep(wait_time)

            # 重试
            can_proceed = await limiter.acquire(estimated_tokens=estimated_tokens)

            if not can_proceed:
                raise Exception("Rate limit exceeded after retry")

        # 调用 LLM
        llm_resp = await asyncio.to_thread(
            _chat_with_messages,
            cli_state.llm_analyzer,
            messages,
            cli_state.current_engine,
        )

        # Debug: print LLM response
        if cli_state.console:
            cli_state.console.print(f"[dim]🔍 LLM Response Type: {type(llm_resp)}[/dim]")
            if isinstance(llm_resp, str):
                cli_state.console.print(f"[dim]🔍 LLM Response (first 100 chars): {llm_resp[:100]}...[/dim]")

        # Handle None response
        if llm_resp is None:
            return {
                "role": "assistant",
                "content": "抱歉，LLM 未返回有效响应。",
            }

        # Convert response to standard format
        if isinstance(llm_resp, str):
            return {
                "role": "assistant",
                "content": llm_resp,
            }
        elif isinstance(llm_resp, dict) and llm_resp.get("type") == "tool_call":
            # Tool call detected
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": llm_resp.get("tool_call_id", "call_1"),
                        "type": "function",
                        "function": {
                            "name": llm_resp.get("name", "execute_cktclaw_command"),
                            "arguments": json.dumps(llm_resp.get("arguments", {})),
                        },
                    }
                ],
            }
        else:
            return {
                "role": "assistant",
                "content": str(llm_resp) if llm_resp else "无响应",
            }

    # Create tool executor function
    async def tool_executor(tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Execute tool via Skill Registry"""
        if tool_name == "execute_cktclaw_command":
            command = tool_args.get("command", "")

            # Try to route to Skill first
            skill_registry = get_skill_registry()

            # Parse command to extract skill name
            skill_name = _extract_skill_name(command)

            if skill_name:
                try:
                    skill = await skill_registry.get_skill(skill_name)
                    if skill and skill.executor:
                        # Execute via Skill
                        context = {"cli_state": cli_state}
                        result = await skill.executor(command, context)

                        # Convert result to string
                        if isinstance(result, list):
                            return "\n".join(
                                item.get("text", str(item))
                                for item in result
                                if isinstance(item, dict)
                            )
                        return str(result)
                except Exception as e:
                    console.print(f"[yellow]⚠️ Skill execution failed, falling back to legacy: {e}[/yellow]")

            # Fallback to legacy execute_cktclaw_command
            tool_output = await asyncio.to_thread(
                execute_cktclaw_command,
                command,
                cli_state,
            )
            return str(tool_output)

        return f"Unknown tool: {tool_name}"

    # Create QueryLoop
    from ..harness.query.query_loop import create_query_loop
    query_loop = create_query_loop(
        llm_func=llm_wrapper,
        tool_executor=tool_executor,
        config=config,
    )

    # ━━━━━━━━━━ 4. Run QueryLoop ━━━━━━━━━━
    with render_spinner(
        console,
        f"{Icons.CIRCUIT} Analyzing with {cli_state.current_engine}...",
    ):
        try:
            # Run QueryLoop
            result = None
            async for partial_result in query_loop.run(messages_dict):
                result = partial_result

                # Show progress
                if result.state == QueryStateEnum.TOOL_EXECUTING:
                    console.print(
                        f"[dim]🔧 Executing tool: {result.current_tool_name}[/dim]"
                    )
                elif result.state == QueryStateEnum.SELF_HEALING:
                    console.print(
                        f"[dim]🔄 Self-healing: {result.error_message}[/dim]"
                    )

            if not result:
                raise ValueError("QueryLoop returned no result")

            # Extract final response
            if result.state == QueryStateEnum.TERMINAL:
                response = result.final_response or "无响应"
            else:
                response = f"Query loop stopped in state: {result.state.value}"

            # Ensure response is not None or empty
            if not response or response.strip() == "":
                response = "抱歉，未能生成有效响应。"

            elapsed = time.time() - start_time

        except Exception as e:
            render_error(
                console,
                f"LLM call failed: {e}",
                error_type="error",
            )
            return

    # ━━━━━━━━━━ 5. Store messages in memory ━━━━━━━━━━
    try:
        from ..cktmem import MessageRole, MessageType, ContextLayer

        # Store user message
        await cli_state.storage.add_message(
            session_id=cli_state.session_id,
            role=MessageRole.USER,
            content=user_message,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )

        # Store assistant response
        await cli_state.storage.add_message(
            session_id=cli_state.session_id,
            role=MessageRole.ASSISTANT,
            content=response,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )
    except Exception as e:
        console.print(f"[yellow]⚠️ Failed to store messages: {e}[/yellow]")

    # ━━━━━━━━━━ 6. Render response ━━━━━━━━━━
    render_user_message(console, user_message)
    render_assistant_message(console, response)
    render_completion_summary(
        console,
        timing_dict={"total": elapsed},
        title=f"Completed with {cli_state.current_engine}",
    )


def _extract_skill_name(command: str) -> Optional[str]:
    """Extract skill name from command string"""
    command = command.strip()

    # Check for skill prefixes
    if command.startswith("/"):
        parts = command.split()
        if len(parts) > 0:
            skill_name = parts[0][1:]  # Remove leading /
            return skill_name

    # Check for direct skill names
    if command.startswith("abc"):
        return "abc"
    elif command.startswith("yosys"):
        return "yosys"
    elif command.startswith("reverse"):
        return "reverse"
    elif command.startswith("opensta"):
        return "opensta"
    elif command.startswith("ai4eda"):
        return "ai4eda"

    return None


def _chat_with_messages(analyzer, messages, engine):
    """Call LLM with messages (synchronous wrapper)"""
    # Map engine to model_choice
    if engine == "logicrt":
        model_choice = "local"
    elif engine == "deepseek":
        model_choice = "deepseek"
    else:
        model_choice = "local"

    # Call the actual method
    return analyzer.chat_with_context(messages, model_choice)


# Import legacy functions for fallback
from .chat_handler import execute_cktclaw_command
