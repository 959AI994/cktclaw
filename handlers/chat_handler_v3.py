"""
Chat Handler V3 - Streaming LLM + Native Function Calling

Uses the v2 LLM providers (cktclaw/llm/) for streaming output and native
function calling. Falls back to chat_handler_v2 for local models (Qwen/CodeV).

v2.1 Enhancements:
- Retry with jittered backoff on API errors
- Provider failover chain (DeepSeek → Claude → OpenAI)
- Context overflow detection + auto-compress
- Error classification (transient vs permanent)
- Tool guardrails (infinite loop prevention, output truncation)
- Concurrent tool execution for read-only tools
- Trajectory logging
"""

import time
import asyncio
import json
import random
import logging
from typing import Optional, List, Dict, Any, Tuple
from rich.console import Console

from ..ui import (
    render_error,
    render_user_message,
    render_completion_summary,
    Icons,
)

logger = logging.getLogger(__name__)

# ━━━━━━━━━━ Error Classification ━━━━━━━━━━


class ErrorCategory:
    """Classifies LLM errors for retry/failover decisions."""
    TRANSIENT = "transient"       # Network timeout, 429, 503 — retry same provider
    CONTEXT_OVERFLOW = "overflow"  # 413, context_length_exceeded — compress and retry
    PROVIDER_DOWN = "down"        # Repeated failures — failover to next provider
    PERMANENT = "permanent"       # 401, 400 bad request — don't retry


def classify_error(error: Exception) -> str:
    """Classify an error to determine retry strategy."""
    err_str = str(error).lower()

    # Context overflow patterns
    overflow_patterns = [
        "context_length_exceeded",
        "maximum context length",
        "token limit",
        "413",
        "request too large",
        "max_tokens",
        "context window",
    ]
    if any(p in err_str for p in overflow_patterns):
        return ErrorCategory.CONTEXT_OVERFLOW

    # Transient patterns (safe to retry)
    transient_patterns = [
        "timeout",
        "429",
        "rate limit",
        "too many requests",
        "503",
        "service unavailable",
        "502",
        "bad gateway",
        "connection",
        "network",
        "temporary",
    ]
    if any(p in err_str for p in transient_patterns):
        return ErrorCategory.TRANSIENT

    # Permanent patterns (don't retry)
    permanent_patterns = [
        "401",
        "unauthorized",
        "403",
        "forbidden",
        "invalid api key",
        "invalid_request",
        "400",
    ]
    if any(p in err_str for p in permanent_patterns):
        return ErrorCategory.PERMANENT

    # Default: treat as transient (safer to retry)
    return ErrorCategory.TRANSIENT


# ━━━━━━━━━━ Retry State ━━━━━━━━━━


class RetryState:
    """Tracks retry attempts and backoff within a single turn."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.attempts = 0
        self.last_error: Optional[str] = None
        self.failovers: List[str] = []

    @property
    def can_retry(self) -> bool:
        return self.attempts < self.max_retries

    def record_attempt(self, error: str) -> None:
        self.attempts += 1
        self.last_error = error

    def get_backoff_delay(self) -> float:
        """Exponential backoff with jitter."""
        delay = self.base_delay * (2 ** (self.attempts - 1))
        jitter = random.uniform(0, delay * 0.3)
        return delay + jitter

    def reset(self) -> None:
        """Reset for a new turn."""
        self.attempts = 0
        self.last_error = None


# ━━━━━━━━━━ Provider Failover ━━━━━━━━━━

# Preferred failover order
FAILOVER_CHAIN = ["deepseek", "claude", "openai", "local"]


def get_next_provider(current: str, router) -> Optional[Any]:
    """Get next available provider in the failover chain."""
    available = router.available_providers
    try:
        idx = FAILOVER_CHAIN.index(current)
    except ValueError:
        idx = -1

    # Try providers after current in the chain
    for name in FAILOVER_CHAIN[idx + 1:]:
        if name in available:
            provider = router.get_provider(name)
            if provider:
                return name, provider

    # Try providers before current (wrap around)
    for name in FAILOVER_CHAIN[:idx]:
        if name in available:
            provider = router.get_provider(name)
            if provider:
                return name, provider

    return None


# ━━━━━━━━━━ Concurrent Tool Execution ━━━━━━━━━━


async def execute_tools_concurrent(
    tool_calls: list,
    registry,
    cli_state,
    guardrails,
    console,
) -> List[Tuple[str, str, str]]:
    """
    Execute tool calls with concurrency for read-only tools.

    Security checks:
    - Pre-execution: validate paths in arguments via PathSandbox
    - Post-execution: scan results via ThreatDetector

    Returns list of (tool_call_id, result_content, status_icon).
    """
    from ..tools.base import ToolContext
    from ..security import PathSandbox, ThreatDetector
    from ..config_loader import get_config
    from ..trajectory import get_trajectory_logger

    # Initialize security layer
    config = get_config()
    sandbox = PathSandbox(
        allowed_roots=config.security_allowed_paths,
        denied_patterns=config.security_blocked_patterns,
    )
    threat_detector = ThreatDetector()
    trajectory = get_trajectory_logger()

    # Separate read-only and mutating tools
    read_only_batch = []
    mutating_batch = []

    for tc in tool_calls:
        # Pre-execution: validate paths in arguments
        is_safe, reason = sandbox.validate_tool_arguments(tc.arguments)
        if not is_safe:
            # Block immediately — don't even classify read_only vs mutating
            trajectory.log_error(
                session_id=cli_state.session_id,
                error=f"Security: {reason}",
                category="security_blocked",
            )
            read_only_batch.append((tc, None, reason))  # Mark as pre-blocked
            continue

        tool = registry.get(tc.name)
        if tool and tool.read_only:
            read_only_batch.append((tc, tool, None))
        else:
            mutating_batch.append((tc, tool))

    results = []

    # Execute read-only tools concurrently
    if read_only_batch:
        async def _exec_one(tc, tool, pre_block_reason):
            # If pre-blocked by security, return immediately
            if pre_block_reason:
                return (tc.id, f"[Security] Blocked: {pre_block_reason}", "[red]BLOCKED[/red]")

            # Check guardrails
            violation = guardrails.check(tc.name, tc.arguments)
            if violation:
                return (tc.id, str(violation), "[yellow]BLOCKED[/yellow]")

            ctx = ToolContext(
                session_id=cli_state.session_id,
                working_dir=getattr(cli_state, 'working_dir', ''),
            )
            try:
                result = await tool.execute(tc.arguments, ctx)
                content = result.output if result.success else f"Error: {result.error}"
                content = guardrails.truncate_output(content, tc.name)

                # Post-execution: threat detection
                threats = threat_detector.detect_in_tool_output(content)
                if threats:
                    high_threats = [t for t in threats if t.severity in ("high", "critical")]
                    if high_threats:
                        content = threat_detector.sanitize_output(content)
                        summary = threat_detector.get_threat_summary(threats)
                        trajectory.log_error(
                            session_id=cli_state.session_id,
                            error=summary,
                            category="threat_detected",
                        )

                icon = "[green]OK[/green]" if result.success else "[red]FAIL[/red]"
            except Exception as e:
                content = f"Tool execution error: {str(e)}"
                icon = "[red]ERR[/red]"
            return (tc.id, content, icon)

        ro_results = await asyncio.gather(
            *[_exec_one(tc, tool, reason) for tc, tool, reason in read_only_batch]
        )
        results.extend(ro_results)

    # Execute mutating tools sequentially
    for tc, tool in mutating_batch:
        # Check guardrails
        violation = guardrails.check(tc.name, tc.arguments)
        if violation:
            results.append((tc.id, str(violation), "[yellow]BLOCKED[/yellow]"))
            continue

        if tool:
            ctx = ToolContext(
                session_id=cli_state.session_id,
                working_dir=getattr(cli_state, 'working_dir', ''),
            )
            try:
                result = await tool.execute(tc.arguments, ctx)
                content = result.output if result.success else f"Error: {result.error}"
                content = guardrails.truncate_output(content, tc.name)

                # Post-execution: threat detection
                threats = threat_detector.detect_in_tool_output(content)
                if threats:
                    high_threats = [t for t in threats if t.severity in ("high", "critical")]
                    if high_threats:
                        content = threat_detector.sanitize_output(content)
                        summary = threat_detector.get_threat_summary(threats)
                        trajectory.log_error(
                            session_id=cli_state.session_id,
                            error=summary,
                            category="threat_detected",
                        )

                icon = "[green]OK[/green]" if result.success else "[red]FAIL[/red]"
            except Exception as e:
                content = f"Tool execution error: {str(e)}"
                icon = "[red]ERR[/red]"
        else:
            # Try legacy skill execution
            content = await _try_legacy_skill(tc.name, tc.arguments, cli_state)
            content = guardrails.truncate_output(content, tc.name)
            icon = "[yellow]LEGACY[/yellow]"

        results.append((tc.id, content, icon))

    return results


# ━━━━━━━━━━ Main Handler ━━━━━━━━━━


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
    from ..tools import get_tool_registry, ToolGuardrails
    from ..tools.base import ToolContext
    from ..trajectory import get_trajectory_logger

    router = get_model_router()
    provider = router.current_provider
    current_provider_name = router.current_name
    if not provider:
        render_error(console, "No LLM provider configured", error_type="error")
        return

    registry = get_tool_registry()
    tool_schemas = registry.get_openai_tools()
    guardrails = ToolGuardrails()
    trajectory = get_trajectory_logger()

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

    # ━━━━━━━━━━ 2b. Context-aware skill injection ━━━━━━━━━━
    await _inject_skill_context(user_message, chat_messages, cli_state)

    # ━━━━━━━━━━ 3. Streaming query loop with retry + failover ━━━━━━━━━━
    start_time = time.time()
    render_user_message(console, user_message)

    max_turns = 12
    final_text = ""
    retry_state = RetryState()
    total_prompt_tokens = 0
    total_completion_tokens = 0

    # Log the user turn
    trajectory.log_user_message(
        session_id=cli_state.session_id,
        content=user_message,
    )

    for turn in range(max_turns):
        # Reset guardrails each turn (the LLM turn, not tool-calling sub-turns)
        guardrails.reset()

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
                                # Tool call repair: fix malformed arguments
                                tc_name = tool_call_names.get(tc.id, "")
                                tc_args = tc.arguments

                                if not tc_args and tool_call_buffers.get(tc.id):
                                    # Arguments not parsed -- try repair
                                    from ..tools.repair import ToolCallRepair
                                    repair = ToolCallRepair()
                                    try:
                                        tc_args = repair.repair_arguments(
                                            tool_call_buffers[tc.id],
                                            registry.get(tc_name).parameters if registry.get(tc_name) else None,
                                        )
                                        trajectory.log_error(
                                            session_id=cli_state.session_id,
                                            error="Tool call arguments repaired for: " + tc_name,
                                            category="tool_repair",
                                        )
                                    except (ValueError, Exception):
                                        tc_args = {}

                                # Tool name repair
                                if tc_name and not registry.get(tc_name):
                                    from ..tools.repair import ToolCallRepair
                                    repair = ToolCallRepair()
                                    fixed_name = repair.repair_tool_name(
                                        tc_name,
                                        list(registry.list_tools().keys()) if hasattr(registry, 'list_tools') else [],
                                    )
                                    if fixed_name:
                                        tc_name = fixed_name

                                tool_calls.append(ToolCall(
                                    id=tc.id,
                                    name=tc_name,
                                    arguments=tc_args,
                                ))

                    if chunk.is_done:
                        # Capture token usage from final chunk
                        if chunk.prompt_tokens:
                            total_prompt_tokens += chunk.prompt_tokens
                        if chunk.completion_tokens:
                            total_completion_tokens += chunk.completion_tokens
                        break

            # Success — reset retry state
            retry_state.reset()

        except Exception as e:
            error_cat = classify_error(e)
            logger.warning(
                f"LLM error (category={error_cat}, provider={current_provider_name}): {e}"
            )

            if error_cat == ErrorCategory.CONTEXT_OVERFLOW:
                # Auto-compress context and retry
                console.print("[yellow]Context too large, compressing...[/yellow]")
                try:
                    # Remove oldest non-system messages
                    if len(chat_messages) > 4:
                        chat_messages = [chat_messages[0]] + chat_messages[-3:]
                    continue
                except Exception:
                    pass

            elif error_cat == ErrorCategory.TRANSIENT and retry_state.can_retry:
                # Retry with backoff
                retry_state.record_attempt(str(e))
                delay = retry_state.get_backoff_delay()
                console.print(
                    f"[yellow]Retrying in {delay:.1f}s "
                    f"(attempt {retry_state.attempts}/{retry_state.max_retries})...[/yellow]"
                )
                await asyncio.sleep(delay)
                continue

            elif error_cat in (ErrorCategory.TRANSIENT, ErrorCategory.PROVIDER_DOWN):
                # Failover to next provider
                failover_result = get_next_provider(current_provider_name, router)
                if failover_result:
                    next_name, next_provider = failover_result
                    console.print(
                        f"[yellow]Failing over: {current_provider_name} → {next_name}[/yellow]"
                    )
                    provider = next_provider
                    current_provider_name = next_name
                    retry_state.reset()
                    retry_state.failovers.append(next_name)
                    continue

            # If we get here, error is unrecoverable
            render_error(console, f"LLM error: {e}", error_type="error")
            trajectory.log_error(
                session_id=cli_state.session_id,
                error=str(e),
                category=error_cat,
            )
            return

        # Render streamed text as Markdown
        if text_buffer.strip():
            from rich.markdown import Markdown
            console.print(Markdown(text_buffer))

        if tool_calls:
            # ━━━━━━━━━━ Execute tool calls (concurrent for read-only) ━━━━━━━━━━
            chat_messages.append(ChatMessage(
                role=MessageRole.ASSISTANT,
                content=text_buffer,
                tool_calls=tool_calls,
            ))

            # Log tool calls
            for tc in tool_calls:
                console.print(
                    f"  [dim]{Icons.CIRCUIT} Calling:[/dim] [bold cyan]{tc.name}[/bold cyan]"
                )
                trajectory.log_tool_call(
                    session_id=cli_state.session_id,
                    tool_name=tc.name,
                    arguments=tc.arguments,
                )

            # Execute tools (concurrent for read-only, sequential for mutating)
            results = await execute_tools_concurrent(
                tool_calls, registry, cli_state, guardrails, console
            )

            # Map results back to tool call IDs for proper ordering
            result_map = {r[0]: r for r in results}
            for tc in tool_calls:
                tc_id, result_content, status_icon = result_map.get(
                    tc.id, (tc.id, "Tool not executed", "[red]ERR[/red]")
                )
                console.print(f"  [dim]  └─ {status_icon} ({len(result_content)} chars)[/dim]")

                chat_messages.append(ChatMessage(
                    role=MessageRole.TOOL,
                    content=result_content,
                    tool_call_id=tc.id,
                ))

                trajectory.log_tool_result(
                    session_id=cli_state.session_id,
                    tool_name=tc.name,
                    result=result_content[:500],
                    success="BLOCKED" not in status_icon and "ERR" not in status_icon,
                )

            continue
        else:
            # No tool calls — this is the final response
            final_text = text_buffer
            break

    elapsed = time.time() - start_time

    # Log assistant response
    trajectory.log_assistant_message(
        session_id=cli_state.session_id,
        content=final_text,
        provider=current_provider_name,
        elapsed=elapsed,
    )

    # Log token usage if available
    if total_prompt_tokens or total_completion_tokens:
        trajectory._write_event(cli_state.session_id, "token_usage", {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
            "provider": current_provider_name,
        })

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
        console.print(f"[yellow]Failed to store messages: {e}[/yellow]")

    # ━━━━━━━━━━ 5. Completion summary ━━━━━━━━━━
    title = f"Completed with {current_provider_name}"
    if retry_state.failovers:
        title += f" (failover from {retry_state.failovers[0]})"

    render_completion_summary(
        console,
        timing_dict={"total": elapsed},
        title=title,
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


# EDA file extensions for skill activation
import re as _re
_EDA_FILE_PATTERN = _re.compile(
    r'\b\w+\.(aig|v|sv|sdc|lib|def|lef|spef|blif|bench)\b', _re.IGNORECASE
)


async def _inject_skill_context(
    user_message: str,
    chat_messages: list,
    cli_state,
) -> None:
    """
    Inject relevant skill descriptions into chat_messages before the LLM call.

    1. If EDA file extensions detected, activate conditional skills for those paths.
    2. Get skill descriptions and inject as a system message.
    """
    from ..harness import get_skill_registry
    from ..llm.base import ChatMessage
    from ..llm.types import MessageRole

    try:
        skill_registry = get_skill_registry()

        # Detect EDA file references in user message
        file_matches = _EDA_FILE_PATTERN.findall(user_message)
        activated_skills = []

        if file_matches:
            # Extract full filenames for conditional skill activation
            file_paths = _re.findall(
                r'\b[\w./\\-]+\.(aig|v|sv|sdc|lib|def|lef|spef|blif|bench)\b',
                user_message,
                _re.IGNORECASE,
            )
            if file_paths:
                cwd = getattr(cli_state, 'working_dir', '.')
                activated_skills = await skill_registry.activate_conditional_skills_for_paths(
                    [fp[0] if isinstance(fp, tuple) else fp for fp in file_paths],
                    cwd,
                )

        # Get skill descriptions for prompt injection
        skill_prompt = await skill_registry.get_skill_descriptions_for_prompt(
            matched_skill_names=activated_skills if activated_skills else None,
        )

        if skill_prompt:
            # Insert after system messages but before user messages
            insert_idx = 0
            for i, msg in enumerate(chat_messages):
                if msg.role != MessageRole.SYSTEM:
                    insert_idx = i
                    break
            else:
                insert_idx = len(chat_messages)

            chat_messages.insert(insert_idx, ChatMessage(
                role=MessageRole.SYSTEM,
                content=skill_prompt,
            ))

    except Exception:
        pass  # Graceful degradation -- never block the chat flow
