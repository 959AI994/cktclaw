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
import re
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
    TerminalReason,
    get_skill_registry,
)

from ..harness.services.api import (
    RateLimiter,
    RateLimitConfig,
)

try:
    from cktclaw.models import LLMVerilogAnalyzer
    from cktclaw import config as _ckt_config
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
            # 估算按「消息字符/4」；长 system + 多轮会话很容易 >100K，会误触发 acquire 失败并 sleep ~60s
            max_tokens_per_minute=2_000_000,
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
    from .intent_router import build_chip_router_context, execution_skill_for_intent, resolve_chip_intent_async
    router_context = build_chip_router_context(cli_state=cli_state)
    provider_label = router_context.get("provider_name") or "none"
    chip_intent = await resolve_chip_intent_async(user_message, router_context)
    detected_skill = execution_skill_for_intent(chip_intent)
    if chip_intent.intent_type == "chip_artifact_query":
        console.print(
            f"[dim]→ Chip route decision: provider={provider_label}, source={chip_intent.router_source}, "
            f"route={chip_intent.route}, confidence={chip_intent.confidence:.2f}"
            f"{', fallback_reason=' + str(chip_intent.fallback_reason) if chip_intent.router_source == 'rules_fallback' else ''}; "
            f"{chip_intent.rationale}[/dim]"
        )
        from .chip_artifact_resolver import render_artifact_query_for_cli, resolve_chip_artifact_query
        query = resolve_chip_artifact_query(chip_intent.artifact_query, context=router_context, cli_state=cli_state)
        console.print(render_artifact_query_for_cli(query))
        return
    if (
        chip_intent.is_execution_route
        and detected_skill
        and chip_intent.confidence >= 0.80
        and not chip_intent.needs_clarification
        and not chip_intent.requires_confirmation
    ):
        console.print(
            f"[dim]→ Auto-routed by {chip_intent.router_source} "
            f"(provider={provider_label}"
            f"{', fallback_reason=' + str(chip_intent.fallback_reason) if chip_intent.router_source == 'rules_fallback' else ''}) "
            f"to {detected_skill}: "
            f"{chip_intent.intent_type}, confidence={chip_intent.confidence:.2f}; "
            f"{chip_intent.rationale}[/dim]"
        )
        chip_domain_skills = {
            "chip-architecture", "chip-rtl", "chip-verification", "chip-formal",
            "chip-synthesis", "chip-dft", "chip-sta", "chip-hls", "chip-pd",
            "chip-soc", "chip-compiler", "chip-firmware", "chip-fpga",
            "chip-infrastructure", "chip-pipeline",
        }
        if detected_skill in chip_domain_skills:
            from .chip_design_handler import handle_chip_design
            await handle_chip_design(detected_skill, user_message, cli_state)
        else:
            from .workflow_skill_handler import process_workflow_skill
            await process_workflow_skill(detected_skill, user_message, cli_state)
        return

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

    # ━━━━━━━━━━ 1.5. Augment user message with exact file paths ━━━━━━━━━━
    # Local models (e.g. Qwen 3B) tend to hallucinate paths; pinning them
    # in the message dramatically reduces wrong-path tool failures.
    _FILE_PATH_RE = re.compile(
        r"(/[\w./-]+\.(?:aig|aiger|v|sv|verilog|lib|lef|def|spef|pt|graphml))",
        re.IGNORECASE,
    )
    _paths_in_msg = _FILE_PATH_RE.findall(user_message)
    if _paths_in_msg and cli_state.current_engine not in ("deepseek",):
        _path_hint = "、".join(_paths_in_msg)
        # Append hint to the last user message only (don't touch history)
        for _msg in reversed(messages_dict):
            if _msg["role"] == "user":
                _msg["content"] += (
                    f"\n\n[重要提示] 本次涉及的文件路径如下，调用工具时必须原样使用，"
                    f"不得修改或猜测：{_path_hint}"
                )
                break

    # ━━━━━━━━━━ 2. Initialize LLM analyzer ━━━━━━━━━━
    if cli_state.llm_analyzer is None:
        cli_state.llm_analyzer = LLMVerilogAnalyzer(
            codev_path=_ckt_config.CODEV_PATH,
            gpu_id=_ckt_config.CODEV_CHAT_GPU_ID,
            verbose=_ckt_config.VERBOSE,
        )

    # ━━━━━━━━━━ 2.5. Build tools from SkillRegistry ━━━━━━━━━━
    skill_registry = get_skill_registry()
    all_skills = await skill_registry.list_skills()

    # 构建工具列表
    tools = []
    for skill in all_skills:
        if skill.user_invocable:  # 只包含用户可调用的技能
            tool_spec = {
                "type": "function",
                "function": {
                    "name": skill.name,
                    "description": f"{skill.description}\n使用场景: {skill.when_to_use}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "args": {
                                "type": "string",
                                "description": f"参数格式: {skill.argument_hint}\n参数名: {', '.join(skill.argument_names)}"
                            }
                        },
                        "required": ["args"],
                    },
                },
            }
            tools.append(tool_spec)

    # 不再添加 execute_cktclaw_command fallback
    # 强制 LLM 只使用注册的专有 EDA Skills


    # ━━━━━━━━━━ 3. Create QueryLoop ━━━━━━━━━━
    start_time = time.time()

    # Get system prompt from context manager
    system_prompt = cli_state.context_manager.system_prompt

    # Configure QueryLoop
    # 工具链场景下模型常多轮只返回 tool_calls；max_turns 过小会在产出正文前被截断 →「无响应」
    config = QueryConfig(
        system_prompt=system_prompt,
        max_turns=12,
        auto_compact_enabled=True,
        auto_compact_threshold=150_000,
        target_tokens=40_000,
    )

    # Create LLM wrapper function
    async def llm_wrapper(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Wrapper for LLM calls with rate limiting"""
        # 仅 DeepSeek 云端需要限流；本地 logicrt 共用限流时会误触发约 60s 等待。
        if cli_state.current_engine == "deepseek":
            limiter = get_rate_limiter()
            estimated_tokens = sum(
                len(str(msg.get("content", ""))) // 4
                for msg in messages
            )
            can_proceed = await limiter.acquire(estimated_tokens=estimated_tokens)

            if not can_proceed:
                wait_time = limiter.get_wait_time()

                if cli_state.console:
                    cli_state.console.print(
                        f"[yellow]⏳ Rate limit reached. Waiting {wait_time:.1f}s...[/yellow]"
                    )

                await asyncio.sleep(wait_time)

                can_proceed = await limiter.acquire(estimated_tokens=estimated_tokens)

                if not can_proceed:
                    raise Exception("Rate limit exceeded after retry")

        # 调用 LLM（传递动态构建的 tools）
        llm_resp = await asyncio.to_thread(
            _chat_with_messages,
            cli_state.llm_analyzer,
            messages,
            cli_state.current_engine,
            tools,  # 传递工具列表
        )

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
        skill_registry = get_skill_registry()

        # Check if tool_name is a registered skill
        try:
            skill = await skill_registry.get_skill(tool_name)
            if skill and skill.executor:
                # Direct skill invocation
                context = {"cli_state": cli_state}
                args_str = tool_args.get("args", "")
                result = await skill.executor(args_str, context)

                # Convert result to string
                if isinstance(result, list):
                    return "\n".join(
                        item.get("text", str(item))
                        for item in result
                        if isinstance(item, dict)
                    )
                return str(result)
        except Exception as e:
            # Skill not found or execution failed, continue to fallback
            if tool_name != "execute_cktclaw_command":
                console.print(f"[yellow]⚠️ Skill '{tool_name}' execution failed: {e}[/yellow]")

        # Handle legacy execute_cktclaw_command
        if tool_name == "execute_cktclaw_command":
            command = tool_args.get("command", "")

            # Try to route to Skill first
            skill_name = _extract_skill_name(command)

            if skill_name:
                try:
                    skill = await skill_registry.get_skill(skill_name)
                    if skill and skill.executor:
                        # Extract arguments (remove skill name from command)
                        if command.startswith("/"):
                            # Format: "/skill_name args..."
                            parts = command.split(maxsplit=1)
                            args_str = parts[1] if len(parts) > 1 else ""
                        else:
                            # Format: "skill_name args..." (legacy)
                            args_str = command[len(skill_name):].strip()

                        # Execute via Skill
                        context = {"cli_state": cli_state}
                        result = await skill.executor(args_str, context)

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
            printed_tool_names = set()
            async for partial_result in query_loop.run(messages_dict):
                result = partial_result

                # Show progress
                if result.state == QueryStateEnum.TOOL_EXECUTING:
                    if result.current_tool_name not in printed_tool_names:
                        printed_tool_names.add(result.current_tool_name)
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
                response = result.final_response
            else:
                response = f"Query loop stopped in state: {result.state.value}"

            # Ensure response is not None or empty（避免仅显示「无响应」而掩盖已有工具输出）
            if not response or str(response).strip() == "":
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

        from ..cktmem.indexing import index_assistant_turn
        index_assistant_turn(
            cli_state.context_manager.semantic_search,
            cli_state.session_id,
            response,
        )
    except Exception as e:
        console.print(f"[yellow]⚠️ Failed to store messages: {e}[/yellow]")

    # ━━━━━━━━━━ 6. Render response ━━━━━━━━━━
    render_user_message(console, user_message)
    render_assistant_message(console, response)
    tool_failures = _count_failed_tool_outputs(getattr(result, "messages", []) if result else [])
    outcome = "completed"
    detail = ""
    if tool_failures:
        outcome = "failed"
        detail = f"{tool_failures} tool result(s) reported failure."
    elif result and result.terminal_reason == TerminalReason.MAX_TURNS:
        outcome = "incomplete"
        detail = "Query loop reached max turns before a clean final answer."
    elif not response or response.strip() in {"抱歉，未能生成有效响应。", "无响应"}:
        outcome = "incomplete"
        detail = "The model did not produce a valid final answer."
    title_prefix = {
        "completed": "Completed",
        "failed": "Failed",
        "incomplete": "Incomplete",
    }[outcome]
    render_completion_summary(
        console,
        timing_dict={"total": elapsed},
        title=f"{title_prefix} with {cli_state.current_engine}",
        status=outcome,
        detail=detail,
    )


def _count_failed_tool_outputs(messages: List[Dict[str, Any]]) -> int:
    failure_markers = (
        "error:",
        "execution error",
        "unknown tool",
        "blocked",
        "failed",
        "status: fail",
        '"status": "fail"',
    )
    count = 0
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content", "")).lower()
        if any(marker in content for marker in failure_markers):
            count += 1
    return count


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


def _chat_with_messages(analyzer, messages, engine, tools=None):
    """Call LLM with messages (synchronous wrapper)"""
    # Map engine to model_choice
    if engine == "logicrt":
        model_choice = "local"
    elif engine == "deepseek":
        model_choice = "deepseek"
    elif engine == "qwen":
        model_choice = "qwen"
    else:
        model_choice = "local"

    # Call the actual method with tools
    return analyzer.chat_with_context(messages, model_choice, tools=tools)


# Import legacy functions for fallback
from .chat_handler import execute_cktclaw_command
