"""
Layered context manager — system / project / session / turn assembly + compaction.

Loads SQLite-backed slices, injects optional file-backed memory prompts, estimates
tokens, and may invoke ``Compactor.auto_compact`` when over budget.
"""

from typing import List, Optional
from .models import (
    Message, MessageRole, MessageType, ContextLayer,
    CompactConfig, CompactionResult
)
from .storage import Storage
from .compactor import Compactor
from .token_counter import TokenCounter
from .memdir import load_memory_prompt


class ContextManager:
    """Builds the multi-layer message list passed to the LLM."""

    def __init__(
        self,
        storage: Storage,
        system_prompt: str,
        config: Optional[CompactConfig] = None,
        project_root: Optional[str] = None,
    ):
        self.storage = storage
        self.system_prompt = system_prompt
        self.config = config or CompactConfig()
        self.compactor = Compactor(storage, self.config)
        self.token_counter = TokenCounter()
        self.project_root = project_root

    async def build_context(
        self,
        session_id: str,
        user_message: str,
        auto_compact: bool = True,
    ) -> List[Message]:
        """
        Compose system + optional memory + project + session + recent turns + user.

        When ``auto_compact`` is enabled and the estimate exceeds the configured
        threshold, ``Compactor.auto_compact`` runs and this method rebuilds from
        the compaction result.
        """
        messages = []

        messages.append(Message(
            role=MessageRole.SYSTEM,
            content=self.system_prompt,
            layer=ContextLayer.SYSTEM,
        ))

        memory_prompt = load_memory_prompt(self.project_root)
        if memory_prompt:
            messages.append(Message(
                role=MessageRole.SYSTEM,
                content=memory_prompt,
                layer=ContextLayer.SYSTEM,
                metadata={"type": "filesystem_memory"},
            ))

        project_messages = await self.storage.get_project_messages(session_id)
        messages.extend(project_messages)

        session_messages = await self._load_session_layer(session_id)
        messages.extend(session_messages)

        turn_messages = await self.storage.get_recent_messages(
            session_id,
            max_rounds=5,
            after_last_boundary=True,
        )
        messages.extend(turn_messages)

        current_message = Message(
            role=MessageRole.USER,
            content=user_message,
            layer=ContextLayer.TURN,
        )
        messages.append(current_message)

        total_tokens = self.token_counter.estimate_messages(messages)

        if auto_compact and total_tokens > self.config.auto_compact_threshold:
            compaction_result = await self.compactor.auto_compact(
                session_id,
                messages,
            )
            if compaction_result:
                messages = await self._rebuild_after_compact(
                    session_id,
                    compaction_result,
                    current_message,
                )

        return messages

    async def _load_session_layer(self, session_id: str) -> List[Message]:
        """Session-layer system snippets (memory index, cores, summaries)."""
        messages = []

        session_memory = await self.storage.format_session_memory(session_id)
        if session_memory:
            messages.append(Message(
                role=MessageRole.SYSTEM,
                content=session_memory,
                msg_type=MessageType.CHAT,
                layer=ContextLayer.SESSION,
                metadata={"type": "session_memory"},
            ))

        core_contexts = await self.storage.get_core_contexts(session_id)
        messages.extend(core_contexts)

        summaries = await self.storage.get_compact_summaries(session_id)
        messages.extend(summaries)

        return messages

    async def _rebuild_after_compact(
        self,
        session_id: str,
        compaction_result: CompactionResult,
        current_message: Message,
    ) -> List[Message]:
        """Reconstruct messages after a successful compaction pass."""
        messages = []

        messages.append(Message(
            role=MessageRole.SYSTEM,
            content=self.system_prompt,
            layer=ContextLayer.SYSTEM,
        ))

        project_messages = await self.storage.get_project_messages(session_id)
        messages.extend(project_messages)

        session_messages = await self._load_session_layer(session_id)
        messages.extend(session_messages)

        await self.storage.add_message(
            session_id=session_id,
            role=compaction_result.boundary_marker.role,
            content=compaction_result.boundary_marker.content,
            msg_type=compaction_result.boundary_marker.msg_type,
            layer=compaction_result.boundary_marker.layer,
            metadata=compaction_result.boundary_marker.metadata,
        )
        messages.append(compaction_result.boundary_marker)

        for summary_msg in compaction_result.summary_messages:
            await self.storage.add_message(
                session_id=session_id,
                role=summary_msg.role,
                content=summary_msg.content,
                msg_type=summary_msg.msg_type,
                layer=summary_msg.layer,
                metadata=summary_msg.metadata,
            )
            messages.append(summary_msg)

        messages.extend(compaction_result.messages_to_keep)

        messages.append(current_message)

        return messages

    async def add_assistant_message(
        self,
        session_id: str,
        content: str,
        tool_calls: Optional[List] = None,
    ):
        """Persist an assistant turn."""
        await self.storage.add_message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=content,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
            tool_calls=tool_calls,
        )

    async def add_tool_result(
        self,
        session_id: str,
        tool_call_id: str,
        content: str,
        name: str,
    ):
        """Persist a tool result row."""
        await self.storage.add_message(
            session_id=session_id,
            role=MessageRole.TOOL,
            content=content,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
            tool_call_id=tool_call_id,
            name=name,
        )

    async def get_context_stats(self, session_id: str) -> dict:
        """Token estimate + compaction counters for dashboards."""
        all_messages = await self.storage.get_messages(session_id)
        total_tokens = self.token_counter.estimate_messages(all_messages)

        session_info = await self.storage.get_session(session_id)

        return {
            "total_messages": len(all_messages),
            "total_tokens": total_tokens,
            "total_compactions": session_info.get("total_compactions", 0) if session_info else 0,
            "last_compact_at": session_info.get("last_compact_at") if session_info else None,
        }
