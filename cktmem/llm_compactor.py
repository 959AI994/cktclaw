"""
LLM Compactor — model-backed context summarization (4th compaction tier).

Uses the cheapest available LLM provider to generate a focused summary
of conversation history, preserving key decisions, circuit results,
and user requirements.
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class LLMCompactor:
    """
    Summarizes conversation messages using an LLM call.

    Falls back to deterministic summary on any failure.
    """

    def __init__(self, provider_name: str = "deepseek"):
        self.provider_name = provider_name

    async def summarize(
        self,
        messages: List["Message"],
        max_summary_tokens: int = 500,
    ) -> Optional[str]:
        """
        Use an LLM to summarize conversation messages.

        Args:
            messages: List of Message objects to summarize.
            max_summary_tokens: Maximum tokens for the summary.

        Returns:
            Summary string, or None if LLM call fails.
        """
        from ..llm import get_model_router
        from ..llm.base import ChatMessage
        from ..llm.types import MessageRole

        # Build the summarization prompt
        prompt = self._build_prompt(messages)
        if not prompt:
            return None

        try:
            router = get_model_router()
            provider = router.get_provider(self.provider_name)
            if not provider:
                # Try any available provider
                provider = router.current_provider
            if not provider:
                logger.debug("No LLM provider available for compaction")
                return None

            # Use non-streaming for simplicity
            chat_messages = [
                ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=(
                        "You are a conversation summarizer for a chip design assistant. "
                        "Produce a concise summary focusing on: key decisions, circuit "
                        "analysis results, user requirements, and tool outcomes. "
                        "Use bullet points. Keep under 500 tokens."
                    ),
                ),
                ChatMessage(
                    role=MessageRole.USER,
                    content=prompt,
                ),
            ]

            response = await provider.chat(
                chat_messages,
                temperature=0.1,
                max_tokens=max_summary_tokens,
            )

            if response.content and len(response.content.strip()) > 20:
                return response.content.strip()

        except Exception as e:
            logger.debug(f"LLM compaction failed: {e}")

        return None

    def estimate_cost(self, messages: List["Message"]) -> float:
        """
        Estimate cost of summarizing these messages.

        Returns estimated cost in USD.
        """
        total_chars = sum(len(m.content) for m in messages)
        # Rough estimate: ~4 chars/token, DeepSeek $0.14/1M input tokens
        estimated_tokens = total_chars / 4
        return (estimated_tokens / 1_000_000) * 0.14

    def _build_prompt(self, messages: List["Message"]) -> str:
        """Build the summarization prompt from messages."""
        from ..cktmem.models import MessageRole

        parts = ["Summarize this conversation:\n"]
        total_chars = 0
        max_chars = 8000  # Don't send too much to the summarizer

        for msg in messages:
            if msg.role in (MessageRole.USER, MessageRole.ASSISTANT):
                prefix = "User" if msg.role == MessageRole.USER else "Assistant"
                content = msg.content[:500]
                entry = f"\n{prefix}: {content}"
                if total_chars + len(entry) > max_chars:
                    break
                parts.append(entry)
                total_chars += len(entry)

        if total_chars < 100:
            return ""  # Not enough content to summarize

        return "".join(parts)


# Avoid circular import at module level
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..cktmem.models import Message
