"""
Tests for LLM providers and ModelRouter.
"""

import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional

import pytest

from cktclaw.llm.base import AsyncLLMProvider, ChatMessage, ChatResponse
from cktclaw.llm.types import MessageRole, StreamChunk, ToolCallDelta
from cktclaw.llm.router import ModelRouter


class MockProvider(AsyncLLMProvider):
    """Mock LLM provider for testing."""
    provider_name = "mock"
    supports_streaming = True
    supports_function_calling = True

    def __init__(self, responses: Optional[List[str]] = None):
        self._responses = responses or ["Hello from mock!"]
        self._call_count = 0

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        tools=None,
        temperature=0.3,
        max_tokens=4096,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        response = self._responses[min(self._call_count, len(self._responses) - 1)]
        self._call_count += 1

        # Simulate streaming word by word
        words = response.split()
        for i, word in enumerate(words):
            yield StreamChunk(text_delta=word + " ")

        yield StreamChunk(
            is_done=True,
            prompt_tokens=10,
            completion_tokens=len(words),
            total_tokens=10 + len(words),
        )

    async def is_available(self) -> bool:
        return True


class MockToolCallingProvider(AsyncLLMProvider):
    """Mock provider that returns tool calls."""
    provider_name = "mock_tools"
    supports_streaming = True
    supports_function_calling = True

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        tools=None,
        temperature=0.3,
        max_tokens=4096,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        # First call returns tool call, second returns text
        has_tool_result = any(m.role == MessageRole.TOOL for m in messages)

        if not has_tool_result and tools:
            yield StreamChunk(
                tool_call_delta=ToolCallDelta(
                    id="call_1",
                    name="dummy",
                    arguments_delta='{"input": "test"}',
                    is_complete=True,
                    arguments={"input": "test"},
                )
            )
            yield StreamChunk(is_done=True)
        else:
            yield StreamChunk(text_delta="Tool result processed.")
            yield StreamChunk(is_done=True)

    async def is_available(self) -> bool:
        return True


class TestChatMessage:
    def test_create_message(self):
        msg = ChatMessage(role=MessageRole.USER, content="hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "hello"

    def test_system_message(self):
        msg = ChatMessage(role=MessageRole.SYSTEM, content="You are helpful.")
        assert msg.role == MessageRole.SYSTEM


class TestMockProvider:
    def test_streaming(self):
        provider = MockProvider(["Hello world"])
        messages = [ChatMessage(role=MessageRole.USER, content="hi")]

        chunks = []
        async def collect():
            async for chunk in provider.chat_stream(messages):
                chunks.append(chunk)

        asyncio.run(collect())
        assert len(chunks) >= 2  # at least one text chunk + done
        text = "".join(c.text_delta for c in chunks)
        assert "Hello" in text
        assert "world" in text

    def test_non_streaming(self):
        provider = MockProvider(["Hello world"])
        messages = [ChatMessage(role=MessageRole.USER, content="hi")]

        response = asyncio.run(provider.chat(messages))
        assert isinstance(response, ChatResponse)
        assert "Hello" in response.content
        assert response.total_tokens > 0

    def test_tool_calling_provider(self):
        provider = MockToolCallingProvider()
        messages = [ChatMessage(role=MessageRole.USER, content="use tool")]

        response = asyncio.run(provider.chat(
            messages,
            tools=[{"type": "function", "function": {"name": "dummy"}}],
        ))
        assert response.has_tool_calls
        assert response.tool_calls[0].name == "dummy"


class TestModelRouter:
    def test_register_and_switch(self):
        router = ModelRouter()
        router.register_provider("mock", MockProvider())
        assert "mock" in router.available_providers
        assert router.switch("mock")
        assert router.current_name == "mock"

    def test_switch_nonexistent(self):
        router = ModelRouter()
        assert not router.switch("nonexistent")

    def test_current_provider(self):
        router = ModelRouter()
        mock = MockProvider()
        router.register_provider("mock", mock)
        router.switch("mock")
        assert router.current_provider is mock

    def test_aliases(self):
        router = ModelRouter()
        router.register_provider("deepseek", MockProvider())
        assert router.switch("ds")
        assert router.current_name == "deepseek"

    def test_summary(self):
        router = ModelRouter()
        router.register_provider("mock", MockProvider())
        summary = router.summary()
        assert "mock" in summary
