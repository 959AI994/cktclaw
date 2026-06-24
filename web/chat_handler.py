"""
Async streaming chat handler for WebSocket-based chat.

Uses ContextManager (same as CLI) for CktClaw system prompt and layered memory.
"""

import asyncio
import logging
import os
from typing import AsyncGenerator, List, Optional

logger = logging.getLogger(__name__)

_context_manager = None


def _get_model_router():
    from ..llm import get_model_router
    return get_model_router()


def _get_storage():
    from .deps import get_web_storage
    return get_web_storage()


def _get_context_manager():
    from .deps import get_web_context_manager
    return get_web_context_manager()


async def _get_capability_registry():
    from ..capability_registry import get_capability_registry
    return get_capability_registry()


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


async def stream_chat(
    *,
    session_id: str,
    user_message: str,
    use_tools: bool = False,
    provider_name: Optional[str] = None,
    attachment_ids: Optional[List[str]] = None,
) -> AsyncGenerator[dict, None]:
    """
    Process a chat message and yield WebSocket-compatible dicts.
    """
    from .bootstrap import ensure_runtime_bootstrapped
    from ..cktmem.models import ContextLayer, MessageRole, MessageType
    from ..llm.types import MessageRole as LLMRole
    from ..llm.base import ChatMessage

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
        logger.warning(f"ensure_session failed: {e}")

    try:
        context_messages = await context_manager.build_context(session_id, enriched_message)
        messages = _cktmem_to_llm(context_messages)
    except Exception as e:
        logger.error(f"build_context failed: {e}")
        messages = [
            ChatMessage(role=LLMRole.SYSTEM, content=context_manager.system_prompt),
            ChatMessage(role=LLMRole.USER, content=enriched_message),
        ]

    tools = None
    if use_tools:
        try:
            cap_reg = await _get_capability_registry()
            entries = await cap_reg.list_all(user_invocable_only=True)
            tools = [e.to_openai_schema() for e in entries if not e.name.startswith("chip-")]
            if not tools:
                tools = None
        except Exception as e:
            logger.debug(f"Failed to load tools: {e}")

    full_content = ""
    tool_calls_in_turn: list[dict] = []
    try:
        async for chunk in provider.chat_stream(messages, tools=tools):
            if chunk.text_delta:
                full_content += chunk.text_delta
                yield {"type": "chat:chunk", "session_id": session_id, "delta": chunk.text_delta}
            if chunk.tool_call_delta:
                tc = chunk.tool_call_delta
                if hasattr(tc, "is_complete") and tc.is_complete:
                    tool_call = {
                        "id": getattr(tc, "id", ""),
                        "name": getattr(tc, "name", ""),
                        "arguments": getattr(tc, "arguments", {}),
                    }
                    tool_calls_in_turn.append(tool_call)
                    yield {"type": "chat:tool_call", "session_id": session_id, "tool_call": tool_call}

                    try:
                        from ..tools.base import ToolContext
                        cap_reg = await _get_capability_registry()
                        ctx = ToolContext(session_id=session_id, working_dir=os.getcwd())
                        result = await cap_reg.execute(tool_call["name"], tool_call["arguments"], ctx)
                        result_str = str(result) if result else ""
                        yield {
                            "type": "chat:tool_result",
                            "session_id": session_id,
                            "tool_call_id": tool_call["id"],
                            "name": tool_call["name"],
                            "content": result_str[:2000],
                        }
                        messages.append(
                            ChatMessage(
                                role=LLMRole.TOOL,
                                content=result_str[:2000],
                                tool_call_id=tool_call["id"],
                                name=tool_call["name"],
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Tool execution failed: {e}")
                        yield {
                            "type": "chat:tool_result",
                            "session_id": session_id,
                            "tool_call_id": tool_call["id"],
                            "name": tool_call["name"],
                            "content": f"Error: {e}",
                        }
            if chunk.is_done:
                break
    except asyncio.CancelledError:
        yield {"type": "chat:error", "session_id": session_id, "error": "Cancelled"}
        if full_content:
            try:
                await storage.add_message(
                    session_id, MessageRole.USER, enriched_message,
                    msg_type=MessageType.CHAT, layer=ContextLayer.TURN,
                )
                await storage.add_message(
                    session_id, MessageRole.ASSISTANT, full_content + " [cancelled]",
                    msg_type=MessageType.CHAT, layer=ContextLayer.TURN,
                )
            except Exception:
                pass
        return
    except Exception as e:
        logger.error(f"Chat stream error: {e}")
        yield {"type": "chat:error", "session_id": session_id, "error": str(e)}
        if full_content:
            full_content += f"\n[Error: {e}]"

    try:
        await storage.add_message(
            session_id, MessageRole.USER, enriched_message,
            msg_type=MessageType.CHAT, layer=ContextLayer.TURN,
        )
        if full_content:
            await storage.add_message(
                session_id, MessageRole.ASSISTANT, full_content,
                msg_type=MessageType.CHAT, layer=ContextLayer.TURN,
            )
            try:
                from ..cktmem.indexing import index_assistant_turn
                index_assistant_turn(
                    context_manager.semantic_search,
                    session_id,
                    full_content,
                )
            except Exception as e:
                logger.debug(f"Semantic index failed: {e}")
    except Exception as e:
        logger.debug(f"Failed to persist messages: {e}")

    yield {
        "type": "chat:done",
        "session_id": session_id,
        "usage": {
            "completion_tokens": len(full_content.split()),
            "tool_calls": len(tool_calls_in_turn),
        },
    }
