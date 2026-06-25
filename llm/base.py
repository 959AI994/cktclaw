"""
AsyncLLMProvider — abstract base class for all LLM providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from .types import MessageRole, StreamChunk, ToolCall


@dataclass
class ChatMessage:
    """A message in a conversation."""
    role: MessageRole
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None  # For tool result messages
    name: Optional[str] = None  # For multi-agent identification


@dataclass
class ChatResponse:
    """Complete (non-streaming) response from LLM."""
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class AsyncLLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All providers support:
    - Streaming chat (yields StreamChunks)
    - Non-streaming chat (returns ChatResponse)
    - Tool/function calling (via tools parameter)

    Subclasses implement the streaming interface; non-streaming
    is provided as a convenience that collects the stream.
    """

    # Provider identification
    provider_name: str = "unknown"
    supports_streaming: bool = True
    supports_function_calling: bool = True

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream a chat completion.

        Args:
            messages: Conversation history.
            tools: Tool definitions in provider-native format.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Yields:
            StreamChunk objects with incremental content.
        """
        ...
        # Make this an async generator
        yield StreamChunk(is_done=True)  # type: ignore

    async def chat(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ChatResponse:
        """
        Non-streaming chat completion (collects stream).

        Default implementation collects from chat_stream().
        Providers can override for more efficient non-streaming API calls.
        """
        content_parts = []
        tool_calls: List[ToolCall] = []
        tool_call_buffers: Dict[str, str] = {}  # id -> accumulated arguments
        tool_call_names: Dict[str, str] = {}  # id -> name
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        async for chunk in self.chat_stream(
            messages, tools, temperature, max_tokens, **kwargs
        ):
            if chunk.text_delta:
                content_parts.append(chunk.text_delta)

            if chunk.tool_call_delta:
                tc = chunk.tool_call_delta
                if tc.id:
                    if tc.id not in tool_call_buffers:
                        tool_call_buffers[tc.id] = ""
                    if tc.name:
                        tool_call_names[tc.id] = tc.name
                    tool_call_buffers[tc.id] += tc.arguments_delta

                    if tc.is_complete:
                        import json
                        try:
                            args = json.loads(tool_call_buffers[tc.id])
                        except json.JSONDecodeError:
                            args = {}
                        tool_calls.append(ToolCall(
                            id=tc.id,
                            name=tool_call_names.get(tc.id, ""),
                            arguments=args,
                        ))

            if chunk.is_done:
                usage["prompt_tokens"] = chunk.prompt_tokens
                usage["completion_tokens"] = chunk.completion_tokens
                usage["total_tokens"] = chunk.total_tokens

        return ChatResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
        )

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is configured and reachable."""
        ...
