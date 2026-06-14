"""
Anthropic Provider — Claude API with tool_use and streaming.
"""

import json
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from .base import AsyncLLMProvider, ChatMessage, ChatResponse
from .types import MessageRole, StreamChunk, ToolCall, ToolCallDelta

logger = logging.getLogger(__name__)


class AnthropicProvider(AsyncLLMProvider):
    """Anthropic Claude API provider with streaming and tool_use."""

    provider_name = "claude"
    supports_streaming = True
    supports_function_calling = True

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        timeout: int = 120,
    ):
        self.api_key = api_key or os.environ.get("CKTCLAW_CLAUDE_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.default_max_tokens = max_tokens
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        """Lazy-load anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("anthropic package required. Install: pip install anthropic")
        return self._client

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream chat completion from Claude API."""
        if not self.api_key:
            yield StreamChunk(text_delta="[Error: ANTHROPIC_API_KEY not set]", is_done=True)
            return

        try:
            client = self._get_client()
        except ImportError as e:
            yield StreamChunk(text_delta=f"[Error: {e}]", is_done=True)
            return

        # Separate system message
        system_content = ""
        api_messages = []
        for msg in messages:
            role = msg.role.value if isinstance(msg.role, MessageRole) else msg.role
            if role == "system":
                system_content += msg.content + "\n"
            elif role == "tool":
                # Convert tool results to Anthropic format
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id or "",
                        "content": msg.content,
                    }],
                })
            else:
                content: Any = msg.content
                if msg.tool_calls:
                    content = []
                    if msg.content:
                        content.append({"type": "text", "text": msg.content})
                    for tc in msg.tool_calls:
                        content.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        })
                api_messages.append({"role": role, "content": content})

        try:
            create_kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": api_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if system_content.strip():
                create_kwargs["system"] = system_content.strip()
            if tools:
                create_kwargs["tools"] = tools

            with client.messages.stream(**create_kwargs) as stream:
                current_tool_id = ""
                current_tool_name = ""
                tool_input_json = ""

                for event in stream:
                    if event.type == "content_block_start":
                        block = event.content_block
                        if hasattr(block, "type"):
                            if block.type == "tool_use":
                                current_tool_id = block.id
                                current_tool_name = block.name
                                tool_input_json = ""

                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if hasattr(delta, "type"):
                            if delta.type == "text_delta":
                                yield StreamChunk(text_delta=delta.text)
                            elif delta.type == "input_json_delta":
                                tool_input_json += delta.partial_json
                                yield StreamChunk(
                                    tool_call_delta=ToolCallDelta(
                                        id=current_tool_id,
                                        name=current_tool_name,
                                        arguments_delta=delta.partial_json,
                                    )
                                )

                    elif event.type == "content_block_stop":
                        if current_tool_id and tool_input_json:
                            try:
                                args = json.loads(tool_input_json)
                            except json.JSONDecodeError:
                                args = {}
                            yield StreamChunk(
                                tool_call_delta=ToolCallDelta(
                                    id=current_tool_id,
                                    name=current_tool_name,
                                    is_complete=True,
                                    arguments=args,
                                )
                            )
                            current_tool_id = ""
                            current_tool_name = ""
                            tool_input_json = ""

                    elif event.type == "message_stop":
                        pass

                # Get final message for usage
                final_message = stream.get_final_message()
                usage = final_message.usage
                yield StreamChunk(
                    is_done=True,
                    prompt_tokens=usage.input_tokens,
                    completion_tokens=usage.output_tokens,
                    total_tokens=usage.input_tokens + usage.output_tokens,
                )

        except Exception as e:
            yield StreamChunk(text_delta=f"[Error: {str(e)}]", is_done=True)

    async def is_available(self) -> bool:
        """Check if Claude API is configured."""
        if not self.api_key:
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False
