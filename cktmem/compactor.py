"""
Context compactor — ordered strategies to shrink overflowing transcripts.

Tries session-memory style tail retention first, then micro tool-output trimming,
then a lightweight deterministic “full” summary placeholder.
"""

from typing import Optional, List
from datetime import datetime
from .models import (
    Message, MessageRole, MessageType, ContextLayer,
    CompactionResult, CompactConfig, CompactBoundary
)
from .token_counter import TokenCounter
from .storage import Storage


class Compactor:
    """Applies compaction policies backed by ``Storage``."""

    def __init__(self, storage: Storage, config: CompactConfig):
        self.storage = storage
        self.config = config
        self.token_counter = TokenCounter()

    async def auto_compact(
        self,
        session_id: str,
        messages: List[Message],
    ) -> Optional[CompactionResult]:
        """
        Run the cheapest successful strategy.

        Order:
        1. Session-memory style retention window
        2. Micro compaction (truncate huge tool payloads)
        3. Full compaction stub (deterministic summary text)
        """
        messages_to_compact = self._get_messages_after_last_boundary(messages)

        if not messages_to_compact:
            return None

        result = await self._try_session_memory_compact(
            session_id,
            messages_to_compact,
        )
        if result:
            return result

        result = await self._try_micro_compact(
            session_id,
            messages_to_compact,
        )
        if result:
            return result

        return await self._full_compact(
            session_id,
            messages_to_compact,
        )

    def _get_messages_after_last_boundary(
        self,
        messages: List[Message],
    ) -> List[Message]:
        """Slice to traffic after the latest ``COMPACT_BOUNDARY`` (else turn layer only)."""
        last_boundary_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].msg_type == MessageType.COMPACT_BOUNDARY:
                last_boundary_idx = i
                break

        if last_boundary_idx >= 0:
            return messages[last_boundary_idx + 1:]
        return [m for m in messages if m.layer == ContextLayer.TURN]

    async def _try_session_memory_compact(
        self,
        session_id: str,
        messages: List[Message],
    ) -> Optional[CompactionResult]:
        """
        Keep a suffix that satisfies ``min_tokens`` + ``min_text_messages``.

        Older prefix rows are dropped logically via boundary + retained tail.
        """
        config = self.config.session_memory

        keep_index = self._calculate_keep_index(messages, config)

        if keep_index <= 0:
            return None

        boundary = self._create_boundary(
            messages,
            compact_type="session_memory",
        )

        messages_to_keep = messages[keep_index:]

        pre_tokens = self.token_counter.estimate_messages(messages)
        post_tokens = self.token_counter.estimate_messages([boundary] + messages_to_keep)

        await self.storage.record_compaction(
            session_id=session_id,
            compact_type="session_memory",
            pre_compact_tokens=pre_tokens,
            post_compact_tokens=post_tokens,
        )

        return CompactionResult(
            boundary_marker=boundary,
            summary_messages=[],
            messages_to_keep=messages_to_keep,
            pre_compact_token_count=pre_tokens,
            post_compact_token_count=post_tokens,
        )

    def _calculate_keep_index(
        self,
        messages: List[Message],
        config,
    ) -> int:
        """Walk from the end until retention thresholds are met."""
        accumulated_tokens = 0
        text_message_count = 0
        keep_index = len(messages)

        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            msg_tokens = self.token_counter.estimate_message(msg)
            accumulated_tokens += msg_tokens

            if msg.role in [MessageRole.USER, MessageRole.ASSISTANT]:
                text_message_count += 1

            if (accumulated_tokens >= config.min_tokens and
                text_message_count >= config.min_text_messages):
                keep_index = i
                break

            if accumulated_tokens >= config.max_tokens:
                keep_index = i
                break

        return keep_index

    async def _try_micro_compact(
        self,
        session_id: str,
        messages: List[Message],
    ) -> Optional[CompactionResult]:
        """
        Truncate oversized ``TOOL`` rows while preserving call metadata.

        No LLM call — purely structural edits.
        """
        cleaned_messages = []
        tokens_saved = 0

        for msg in messages:
            if self._should_clear_tool_result(msg):
                cleaned = self._clear_tool_result(msg)
                cleaned_messages.append(cleaned)
                tokens_saved += (
                    self.token_counter.estimate_message(msg) -
                    self.token_counter.estimate_message(cleaned)
                )
            else:
                cleaned_messages.append(msg)

        if tokens_saved < 5000:
            return None

        boundary = self._create_boundary(messages, compact_type="micro")

        pre_tokens = self.token_counter.estimate_messages(messages)
        post_tokens = self.token_counter.estimate_messages([boundary] + cleaned_messages)

        await self.storage.record_compaction(
            session_id=session_id,
            compact_type="micro",
            pre_compact_tokens=pre_tokens,
            post_compact_tokens=post_tokens,
        )

        return CompactionResult(
            boundary_marker=boundary,
            summary_messages=[],
            messages_to_keep=cleaned_messages,
            pre_compact_token_count=pre_tokens,
            post_compact_token_count=post_tokens,
        )

    def _should_clear_tool_result(self, msg: Message) -> bool:
        """True for long tool bodies that are safe to shrink heuristically."""
        if msg.role != MessageRole.TOOL:
            return False

        if len(msg.content) < 1000:
            return False

        return True

    def _clear_tool_result(self, msg: Message) -> Message:
        """Keep the first 200 characters plus a compaction notice."""
        truncated_content = msg.content[:200] + "\n... [truncated for compaction]"

        return Message(
            role=msg.role,
            content=truncated_content,
            msg_type=msg.msg_type,
            layer=msg.layer,
            created_at=msg.created_at,
            metadata={**msg.metadata, "truncated": True},
            tool_calls=msg.tool_calls,
            tool_call_id=msg.tool_call_id,
            name=msg.name,
        )

    async def _full_compact(
        self,
        session_id: str,
        messages: List[Message],
    ) -> CompactionResult:
        """
        Deterministic placeholder for LLM-grade summarization.

        (``_build_compact_prompt`` is ready for a future model-backed pass.)
        """
        _ = self._build_compact_prompt(messages)  # reserved for future LLM-backed compaction

        summary = self._generate_simple_summary(messages)

        boundary = self._create_boundary(messages, compact_type="auto")
        summary_message = Message(
            role=MessageRole.USER,
            content=summary,
            msg_type=MessageType.COMPACT_SUMMARY,
            layer=ContextLayer.SESSION,
            metadata={"is_compact_summary": True},
        )

        pre_tokens = self.token_counter.estimate_messages(messages)
        post_tokens = self.token_counter.estimate_messages([boundary, summary_message])

        await self.storage.record_compaction(
            session_id=session_id,
            compact_type="auto",
            pre_compact_tokens=pre_tokens,
            post_compact_tokens=post_tokens,
        )

        return CompactionResult(
            boundary_marker=boundary,
            summary_messages=[summary_message],
            messages_to_keep=[],
            pre_compact_token_count=pre_tokens,
            post_compact_token_count=post_tokens,
        )

    def _build_compact_prompt(self, messages: List[Message]) -> str:
        """Template prompt for a future summarizer model."""
        prompt = "Please summarize the following conversation, focusing on:\n"
        prompt += "1. Key decisions made\n"
        prompt += "2. Important circuit analysis results\n"
        prompt += "3. User requirements and constraints\n\n"

        for msg in messages:
            if msg.role in [MessageRole.USER, MessageRole.ASSISTANT]:
                prompt += f"{msg.role.value}: {msg.content[:500]}\n\n"

        return prompt

    def _generate_simple_summary(self, messages: List[Message]) -> str:
        """Cheap summary without calling an LLM."""
        user_messages = [m for m in messages if m.role == MessageRole.USER]
        assistant_messages = [m for m in messages if m.role == MessageRole.ASSISTANT]

        summary = "## Conversation Summary\n\n"
        summary += f"Total messages: {len(messages)}\n"
        summary += f"User messages: {len(user_messages)}\n"
        summary += f"Assistant messages: {len(assistant_messages)}\n\n"

        if user_messages:
            summary += "### Key User Questions:\n"
            for i, msg in enumerate(user_messages[:3], 1):
                summary += f"{i}. {msg.content[:100]}...\n"

        return summary

    def _create_boundary(
        self,
        messages: List[Message],
        compact_type: str,
    ) -> Message:
        """System message marking the compaction cut."""
        pre_tokens = self.token_counter.estimate_messages(messages)

        boundary_data = CompactBoundary(
            pre_compact_tokens=pre_tokens,
            compact_type=compact_type,
            timestamp=datetime.now(),
        )

        content = "━━━ COMPACT BOUNDARY ━━━\n"
        content += "Previous conversation has been summarized.\n"
        content += f"Pre-compact tokens: {pre_tokens}\n"
        content += f"Compact type: {compact_type}\n"
        content += f"Timestamp: {boundary_data.timestamp.isoformat()}"

        return Message(
            role=MessageRole.SYSTEM,
            content=content,
            msg_type=MessageType.COMPACT_BOUNDARY,
            layer=ContextLayer.SESSION,
            metadata={
                "type": "compact_boundary",
                "pre_compact_tokens": pre_tokens,
                "compact_type": compact_type,
            },
        )
