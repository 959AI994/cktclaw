"""
DeepSeek Provider — streaming chat with native function calling.
"""

import json
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

import requests

from .base import AsyncLLMProvider, ChatMessage, ChatResponse
from .types import MessageRole, StreamChunk, ToolCall, ToolCallDelta

logger = logging.getLogger(__name__)


class DeepSeekProvider(AsyncLLMProvider):
    """DeepSeek API provider with streaming and function calling."""

    provider_name = "deepseek"
    supports_streaming = True
    supports_function_calling = True

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout: int = 120,
    ):
        self.api_key = api_key or os.environ.get("CKTCLAW_DEEPSEEK_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
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
        """Stream chat completion from DeepSeek API."""
        if not self.api_key:
            yield StreamChunk(text_delta="[Error: DEEPSEEK_API_KEY not set]", is_done=True)
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
                f"{self.base_url}/v1/chat/completions",
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
                    # Emit any pending tool calls as complete
                    for idx, tc_data in tool_call_accum.items():
                        try:
                            args = json.loads(tc_data.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamChunk(
                            tool_call_delta=ToolCallDelta(
                                id=tc_data.get("id", ""),
                                name=tc_data.get("name", ""),
                                arguments_delta="",
                                is_complete=True,
                                arguments=args,
                            )
                        )
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

                # Text content
                content = delta.get("content", "")
                if content:
                    yield StreamChunk(text_delta=content)

                # Tool calls
                tool_calls = delta.get("tool_calls", [])
                for tc in tool_calls:
                    idx = tc.get("index", 0)
                    if idx not in tool_call_accum:
                        tool_call_accum[idx] = {
                            "id": tc.get("id", ""),
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments": "",
                        }
                    else:
                        if tc.get("id"):
                            tool_call_accum[idx]["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            tool_call_accum[idx]["name"] = fn["name"]

                    fn = tc.get("function", {})
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

                # Check for finish
                finish_reason = choices[0].get("finish_reason")
                if finish_reason:
                    usage = data.get("usage", {})
                    # Complete pending tool calls
                    for idx_key, tc_data in tool_call_accum.items():
                        try:
                            args = json.loads(tc_data.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamChunk(
                            tool_call_delta=ToolCallDelta(
                                id=tc_data.get("id", ""),
                                name=tc_data.get("name", ""),
                                arguments_delta="",
                                is_complete=True,
                                arguments=args,
                            )
                        )

                    yield StreamChunk(
                        is_done=True,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                    )
                    return

        except requests.exceptions.Timeout:
            yield StreamChunk(text_delta="[Error: Request timed out]", is_done=True)
        except requests.exceptions.RequestException as e:
            yield StreamChunk(text_delta=f"[Error: {str(e)}]", is_done=True)

    async def is_available(self) -> bool:
        """Check if DeepSeek API is configured."""
        return bool(self.api_key)

    def _format_messages(self, messages: List[ChatMessage]) -> List[Dict[str, Any]]:
        """Convert ChatMessage objects to DeepSeek API format."""
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
            if msg.name:
                entry["name"] = msg.name
            formatted.append(entry)
        return formatted
