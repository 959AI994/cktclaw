"""
Async streaming chat handler for WebSocket-based chat.

Multi-turn agent loop with automatic tool calling (aligned with CLI v3),
intent routing with orchestrator confirmation gate, and DSML/text tool fallback.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import AsyncGenerator, List, Optional

logger = logging.getLogger(__name__)

ORCHESTRATOR_CONFIDENCE_THRESHOLD = 0.85
MAX_AGENT_TURNS = 12


def _get_model_router():
    from ..llm import get_model_router
    return get_model_router()


def _get_storage():
    from .deps import get_web_storage
    return get_web_storage()


def _get_context_manager():
    from .deps import get_web_context_manager
    return get_web_context_manager()


async def _ensure_session(storage, session_id: str) -> None:
    session = await storage.get_session(session_id)
    if session is None:
        await storage.create_session(
            session_id=session_id,
            project_name=os.path.basename(os.getcwd()),
            working_dir=os.getcwd(),
        )


def _cktmem_to_llm(messages) -> list:
    from ..llm.base import ChatMessage
    from ..llm.types import MessageRole as LLMRole
    from ..cktmem.models import MessageRole as CktRole

    role_map = {
        CktRole.SYSTEM: LLMRole.SYSTEM,
        CktRole.USER: LLMRole.USER,
        CktRole.ASSISTANT: LLMRole.ASSISTANT,
        CktRole.TOOL: LLMRole.TOOL,
        "system": LLMRole.SYSTEM,
        "user": LLMRole.USER,
        "assistant": LLMRole.ASSISTANT,
        "tool": LLMRole.TOOL,
    }

    result: List[ChatMessage] = []
    for m in messages:
        role = getattr(m, "role", None)
        if hasattr(role, "value"):
            role = role.value
        llm_role = role_map.get(role, LLMRole.USER)
        content = getattr(m, "content", "") or ""
        kwargs = {}
        if getattr(m, "tool_call_id", None):
            kwargs["tool_call_id"] = m.tool_call_id
        if getattr(m, "name", None):
            kwargs["name"] = m.name
        result.append(ChatMessage(role=llm_role, content=str(content), **kwargs))
    return result


def _looks_like_dsml(text: str) -> bool:
    upper = text.upper()
    return "DSML" in upper or "<TOOL_CALL>" in upper


def _build_tool_recommendations(route: dict) -> str:
    skill = route.get("skill_id") or ""
    conf = route.get("confidence", 0)
    lines = [
        "\n\n---",
        f"**推荐：** 检测到与 **{skill}** 相关的芯片设计意图（置信度 {conf:.0%}）。",
        f"- 可在 Chat 中直接描述具体任务，我会调用相关工具；",
        f"- 或前往 **Agents → {skill}** 运行完整 Orchestrator 流水线。",
    ]
    return "\n".join(lines)


async def stream_chat(
    *,
    session_id: str,
    user_message: str,
    use_tools: bool = True,
    disable_tools: bool = False,
    skip_orchestrator_confirm: bool = False,
    force_agent: bool = False,
    provider_name: Optional[str] = None,
    attachment_ids: Optional[List[str]] = None,
) -> AsyncGenerator[dict, None]:
    """
    Process a chat message and yield WebSocket-compatible dicts.

    Tools are enabled by default (use_tools=True). Pass disable_tools=True to
    skip tool schemas entirely. Orchestrator routing uses confidence >= 0.85.
    """
    from .bootstrap import ensure_runtime_bootstrapped
    from ..cktmem.models import ContextLayer, MessageRole, MessageType
    from ..llm.types import MessageRole as LLMRole, ToolCall
    from ..llm.base import ChatMessage
    from ..utils.tool_call_parser import ToolCallParser
    from .agent_loop import (
        accumulate_tool_call_delta,
        append_assistant_tool_round,
        execute_tool_calls,
        load_tool_schemas,
        make_tool_parser,
        parse_text_tool_calls,
    )

    ensure_runtime_bootstrapped()

    from .uploads import build_attachment_context, resolve_uploads

    uploads = resolve_uploads(session_id, attachment_ids)
    attachment_block = build_attachment_context(uploads)
    enriched_message = user_message.strip()
    if attachment_block:
        enriched_message = (enriched_message + attachment_block) if enriched_message else attachment_block.strip()
    if not enriched_message:
        yield {"type": "chat:error", "session_id": session_id, "error": "Empty message"}
        return

    # ── Intent routing (orchestrator gate) ──
    low_confidence_route: Optional[dict] = None
    if not force_agent:
        try:
            from ..capability_registry import get_capability_registry
            cap_reg = get_capability_registry()
            route = await cap_reg.resolve_intent(enriched_message)
            if route and route.get("needs_orchestrator"):
                confidence = float(route.get("confidence") or 0)
                if confidence >= ORCHESTRATOR_CONFIDENCE_THRESHOLD:
                    skill_id = route.get("skill_id", "")
                    if skip_orchestrator_confirm:
                        from .routers.orchestrator import launch_orchestrator_from_chat
                        run_info = await launch_orchestrator_from_chat(
                            skill=skill_id,
                            task=route.get("task") or enriched_message,
                            session_id=session_id,
                            attachment_ids=attachment_ids,
                        )
                        yield {
                            "type": "chat:orchestrator_started",
                            "session_id": session_id,
                            "run_id": run_info["run_id"],
                            "skill": skill_id,
                            "task": route.get("task") or enriched_message,
                        }
                        yield {
                            "type": "chat:done",
                            "session_id": session_id,
                            "usage": {"orchestrator": True},
                        }
                        return
                    yield {
                        "type": "chat:orchestrator_proposal",
                        "session_id": session_id,
                        "proposal_id": f"prop-{uuid.uuid4().hex[:10]}",
                        "skill": skill_id,
                        "task": route.get("task") or enriched_message,
                        "confidence": confidence,
                        "estimated_stages": 6,
                        "estimated_minutes": 5,
                    }
                    return
                elif confidence > 0:
                    low_confidence_route = route
        except Exception as e:
            logger.debug("Intent routing failed: %s", e)

    router = _get_model_router()
    router.initialize()
    provider = router.current_provider if not provider_name else router.get_provider(provider_name)
    if provider is None:
        yield {"type": "chat:error", "session_id": session_id, "error": "No LLM provider available"}
        return

    storage = _get_storage()
    context_manager = _get_context_manager()

    try:
        await _ensure_session(storage, session_id)
    except Exception as e:
        logger.warning("ensure_session failed: %s", e)

    try:
        context_messages = await context_manager.build_context(session_id, enriched_message)
        messages = _cktmem_to_llm(context_messages)
    except Exception as e:
        logger.error("build_context failed: %s", e)
        messages = [
            ChatMessage(role=LLMRole.SYSTEM, content=context_manager.system_prompt),
            ChatMessage(role=LLMRole.USER, content=enriched_message),
        ]

    tools_enabled = use_tools and not disable_tools
    tool_schemas, tool_names = await load_tool_schemas(disable_tools=not tools_enabled)
    parser = make_tool_parser(tool_names)

    working_dir = os.getcwd()
    final_text = ""
    total_tool_calls = 0
    streamed_any = False

    try:
        for _turn in range(MAX_AGENT_TURNS):
            text_buffer = ""
            tool_calls: List[ToolCall] = []
            tool_call_buffers: dict = {}
            tool_call_names: dict = {}
            in_dsml_block = False

            async for chunk in provider.chat_stream(
                messages,
                tools=tool_schemas if tool_schemas else None,
                temperature=0.3,
                max_tokens=4096,
            ):
                if chunk.text_delta:
                    text_buffer += chunk.text_delta
                    if _looks_like_dsml(text_buffer):
                        in_dsml_block = True
                    if not in_dsml_block:
                        yield {
                            "type": "chat:chunk",
                            "session_id": session_id,
                            "delta": chunk.text_delta,
                        }
                        streamed_any = True

                if chunk.tool_call_delta:
                    tc = accumulate_tool_call_delta(
                        chunk.tool_call_delta,
                        tool_call_buffers,
                        tool_call_names,
                    )
                    if tc:
                        tool_calls.append(tc)

                if chunk.is_done:
                    break

            # Text / DSML fallback when native tool_calls absent
            if not tool_calls and text_buffer.strip() and tools_enabled:
                tool_calls = parse_text_tool_calls(text_buffer, parser)

            clean_text = ToolCallParser.strip_tool_markup(text_buffer)
            if clean_text != text_buffer and streamed_any:
                yield {
                    "type": "chat:content_replace",
                    "session_id": session_id,
                    "content": clean_text,
                }

            if tool_calls:
                results = await execute_tool_calls(
                    tool_calls,
                    session_id=session_id,
                    working_dir=working_dir,
                )
                for tc, result_text in results:
                    total_tool_calls += 1
                    yield {
                        "type": "chat:tool_call",
                        "session_id": session_id,
                        "tool_call": {
                            "id": tc.id,
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    yield {
                        "type": "chat:tool_result",
                        "session_id": session_id,
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": result_text[:2000],
                    }

                append_assistant_tool_round(messages, text_buffer, tool_calls, results)
                streamed_any = False
                continue

            final_text = clean_text
            break

    except asyncio.CancelledError:
        yield {"type": "chat:error", "session_id": session_id, "error": "Cancelled"}
        saved = final_text
        try:
            saved = saved or ToolCallParser.strip_tool_markup(locals().get("text_buffer", ""))
        except Exception:
            pass
        if saved:
            try:
                from ..cktmem.models import MessageRole, MessageType, ContextLayer
                await storage.add_message(
                    session_id, MessageRole.USER, enriched_message,
                    msg_type=MessageType.CHAT, layer=ContextLayer.TURN,
                )
                await storage.add_message(
                    session_id, MessageRole.ASSISTANT, saved + " [cancelled]",
                    msg_type=MessageType.CHAT, layer=ContextLayer.TURN,
                )
            except Exception:
                pass
        return
    except Exception as e:
        logger.error("Chat stream error: %s", e)
        yield {"type": "chat:error", "session_id": session_id, "error": str(e)}
        if final_text:
            final_text += f"\n[Error: {e}]"

    if low_confidence_route and final_text:
        final_text += _build_tool_recommendations(low_confidence_route)

    try:
        await storage.add_message(
            session_id, MessageRole.USER, enriched_message,
            msg_type=MessageType.CHAT, layer=ContextLayer.TURN,
        )
        if final_text:
            await storage.add_message(
                session_id, MessageRole.ASSISTANT, final_text,
                msg_type=MessageType.CHAT, layer=ContextLayer.TURN,
            )
            try:
                from ..cktmem.indexing import index_assistant_turn
                index_assistant_turn(
                    context_manager.semantic_search,
                    session_id,
                    final_text,
                )
            except Exception as e:
                logger.debug("Semantic index failed: %s", e)
    except Exception as e:
        logger.debug("Failed to persist messages: %s", e)

    yield {
        "type": "chat:done",
        "session_id": session_id,
        "usage": {
            "completion_tokens": len(final_text.split()) if final_text else 0,
            "tool_calls": total_tool_calls,
        },
    }
