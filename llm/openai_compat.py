"""
OpenAI-Compatible Provider — works with OpenAI, vLLM, Ollama, etc.
"""

import json
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from .base import AsyncLLMProvider, ChatMessage, ChatResponse
from .types import MessageRole, StreamChunk, ToolCall, ToolCallDelta

logger = logging.getLogger(__name__)


class OpenAICompatProvider(AsyncLLMProvider):
    """OpenAI SDK-compatible provider (OpenAI, vLLM, Ollama, etc.)."""

    provider_name = "openai"
    supports_streaming = True
    supports_function_calling = True

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        timeout: int = 120,
    ):
        self.api_key = api_key or os.environ.get("CKTCLAW_OPENAI_KEY") or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream using OpenAI-compatible API."""
        import requests

        if not self.api_key:
            yield StreamChunk(text_delta="[Error: OPENAI_API_KEY not set]", is_done=True)
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=self.timeout,
            )
            response.raise_for_status()

            tool_call_accum: Dict[int, Dict[str, str]] = {}

            for line in response.iter_lines():
                if not line:
                    continue

                line_str = line.decode("utf-8")
                if not line_str.startswith("data: "):
                    continue

                data_str = line_str[6:]
                if data_str.strip() == "[DONE]":
                    yield StreamChunk(is_done=True)
                    return

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = data.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                finish_reason = choices[0].get("finish_reason")

                # Text content
                content = delta.get("content", "")
                if content:
                    yield StreamChunk(text_delta=content)

                # Tool calls
                tool_calls = delta.get("tool_calls", [])
                for tc in tool_calls:
                    idx = tc.get("index", 0)
                    if idx not in tool_call_accum:
                        tool_call_accum[idx] = {"id": "", "name": "", "arguments": ""}

                    if tc.get("id"):
                        tool_call_accum[idx]["id"] = tc["id"]
                    fn = tc.get("function", {})
                    if fn.get("name"):
                        tool_call_accum[idx]["name"] = fn["name"]
                    arg_delta = fn.get("arguments", "")
                    if arg_delta:
                        tool_call_accum[idx]["arguments"] += arg_delta
                        yield StreamChunk(
                            tool_call_delta=ToolCallDelta(
                                id=tool_call_accum[idx]["id"],
                                name=tool_call_accum[idx]["name"],
                                arguments_delta=arg_delta,
                            )
                        )

                if finish_reason:
                    # Complete tool calls
                    for idx_key, tc_data in tool_call_accum.items():
                        try:
                            args = json.loads(tc_data["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamChunk(
                            tool_call_delta=ToolCallDelta(
                                id=tc_data["id"],
                                name=tc_data["name"],
                                is_complete=True,
                                arguments=args,
                            )
                        )

                    usage = data.get("usage", {})
                    yield StreamChunk(
                        is_done=True,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                    )
                    return

        except Exception as e:
            yield StreamChunk(text_delta=f"[Error: {str(e)}]", is_done=True)

    async def is_available(self) -> bool:
        """Check if OpenAI API is configured."""
        return bool(self.api_key)

    def _format_messages(self, messages: List[ChatMessage]) -> List[Dict[str, Any]]:
        """Convert to OpenAI API format."""
        formatted = []
        for msg in messages:
            entry: Dict[str, Any] = {
                "role": msg.role.value if isinstance(msg.role, MessageRole) else msg.role,
                "content": msg.content,
            }
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            formatted.append(entry)
        return formatted
