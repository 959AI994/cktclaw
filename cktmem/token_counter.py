"""
Token 估算器

策略：
- 文本：使用 tiktoken 或粗估（1 token ≈ 4 chars）
- 工具调用：name + input JSON
- 最后乘以 4/3 保守系数
"""

from typing import List
from .models import Message


class TokenCounter:
    """Token 估算器"""

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
        """估算消息列表的 token 数"""
        total = 0
        for msg in messages:
            total += self.estimate_message(msg)
        return int(total * 4 / 3)  # 保守系数

    def estimate_message(self, message: Message) -> int:
        """估算单条消息的 token 数"""
        tokens = 0

        # 内容
        if message.content:
            tokens += self._estimate_text(message.content)

        # 工具调用
        if message.tool_calls:
            for tool_call in message.tool_calls:
                tokens += self._estimate_text(
                    tool_call.get("function", {}).get("name", "") +
                    str(tool_call.get("function", {}).get("arguments", ""))
                )

        return tokens

    def _estimate_text(self, text: str) -> int:
        """估算文本 token 数"""
        if self.use_tiktoken and self.encoder:
            return len(self.encoder.encode(text))
        else:
            # 粗估：1 token ≈ 4 chars
            return len(text) // 4
