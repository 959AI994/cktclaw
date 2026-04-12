"""
Token estimator for compaction heuristics.

Uses ``tiktoken`` when installed, otherwise char-length heuristics, then applies
a conservative 4/3 multiplier to avoid under-budgeting.
"""

from typing import List
from .models import Message


class TokenCounter:
    """Rough token accounting for ``Message`` lists."""

    def __init__(self):
        self.use_tiktoken = False
        self.encoder = None

        try:
            import tiktoken
            self.encoder = tiktoken.encoding_for_model("gpt-4")
            self.use_tiktoken = True
        except Exception:
            pass

    def estimate_messages(self, messages: List[Message]) -> int:
        """Sum per-message estimates with a safety multiplier."""
        total = 0
        for msg in messages:
            total += self.estimate_message(msg)
        return int(total * 4 / 3)

    def estimate_message(self, message: Message) -> int:
        """Content tokens plus serialized tool call payloads."""
        tokens = 0

        if message.content:
            tokens += self._estimate_text(message.content)

        if message.tool_calls:
            for tool_call in message.tool_calls:
                tokens += self._estimate_text(
                    tool_call.get("function", {}).get("name", "") +
                    str(tool_call.get("function", {}).get("arguments", ""))
                )

        return tokens

    def _estimate_text(self, text: str) -> int:
        """Character- or tiktoken-based estimate."""
        if self.use_tiktoken and self.encoder:
            return len(self.encoder.encode(text))
        return len(text) // 4
