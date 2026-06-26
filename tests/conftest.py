"""
Shared test fixtures for CktClaw E2E tests.

Provides:
- MockLLMProvider: Returns canned responses with optional tool calls
- MockToolExecutor: Records calls and returns predefined outputs
- Config fixtures with tmp_path isolation
"""

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
from dataclasses import dataclass, field

import pytest

pytest_plugins = []


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e_live: live E2E gate tests (fixtures/doctor, no auto DeepSeek)")


from cktclaw.llm.base import AsyncLLMProvider, ChatMessage, ChatResponse
from cktclaw.llm.types import MessageRole, StreamChunk, ToolCall, ToolCallDelta
from cktclaw.tools.base import BaseTool, ToolContext, ToolResult
from cktclaw.trajectory import TrajectoryLogger


# ━━━━━━━━━━ Mock LLM Provider ━━━━━━━━━━


class MockLLMProvider(AsyncLLMProvider):
    """
    Mock LLM provider that returns canned responses.

    Usage:
        provider = MockLLMProvider(responses=[
            {"text": "Hello!", "tool_calls": []},
            {"text": "", "tool_calls": [{"id": "tc1", "name": "yosys", "arguments": {...}}]},
        ])
    """

    provider_name = "mock"
    supports_streaming = True
    supports_function_calling = True

    def __init__(
        self,
        responses: Optional[List[Dict[str, Any]]] = None,
        raise_on_call: Optional[Exception] = None,
    ):
        self.responses = responses or [{"text": "Mock response", "tool_calls": []}]
        self.raise_on_call = raise_on_call
        self.call_count = 0
        self.received_messages: List[List[ChatMessage]] = []

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Yield canned response as stream chunks."""
        self.received_messages.append(messages)

        if self.raise_on_call:
            raise self.raise_on_call

        # Get response for this call (cycle through responses)
        idx = self.call_count % len(self.responses)
        response = self.responses[idx]
        self.call_count += 1

        # Yield text
        text = response.get("text", "")
        if text:
            yield StreamChunk(text_delta=text)

        # Yield tool calls
        for tc in response.get("tool_calls", []):
            yield StreamChunk(tool_call_delta=ToolCallDelta(
                id=tc["id"],
                name=tc["name"],
                arguments_delta=json.dumps(tc.get("arguments", {})),
                is_complete=True,
                arguments=tc.get("arguments", {}),
            ))

        # Final chunk with usage
        yield StreamChunk(
            is_done=True,
            prompt_tokens=response.get("prompt_tokens", 100),
            completion_tokens=response.get("completion_tokens", 50),
            total_tokens=response.get("total_tokens", 150),
        )

    async def is_available(self) -> bool:
        return True


# ━━━━━━━━━━ Mock Tool ━━━━━━━━━━


class MockTool(BaseTool):
    """A mock tool that records calls and returns predefined output."""

    def __init__(
        self,
        name: str = "mock_tool",
        output: str = "mock output",
        read_only: bool = False,
        should_fail: bool = False,
    ):
        self.name = name
        self.description = f"Mock tool: {name}"
        self.parameters = {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input argument"},
            },
            "required": [],
        }
        self.read_only = read_only
        self.category = "test"
        self._output = output
        self._should_fail = should_fail
        self.call_history: List[Dict[str, Any]] = []

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        self.call_history.append({"params": params, "context": context})
        if self._should_fail:
            return ToolResult.fail("Mock failure")
        return ToolResult.ok(self._output)


# ━━━━━━━━━━ Mock Registry ━━━━━━━━━━


class MockToolRegistry:
    """Mock tool registry that holds configured tools."""

    def __init__(self, tools: Optional[Dict[str, BaseTool]] = None):
        self._tools = tools or {}

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def list_tools(self) -> Dict[str, BaseTool]:
        return self._tools.copy()


# ━━━━━━━━━━ Fixtures ━━━━━━━━━━


@pytest.fixture
def mock_provider():
    """Basic mock LLM provider."""
    return MockLLMProvider()


@pytest.fixture
def mock_tool():
    """Basic mock tool."""
    return MockTool()


@pytest.fixture
def trajectory_logger(tmp_path):
    """Trajectory logger writing to temp directory."""
    return TrajectoryLogger(base_dir=tmp_path)


@pytest.fixture
def mock_config(tmp_path):
    """Create a temporary config file and return CktClawConfig."""
    from cktclaw.config_loader import CktClawConfig

    config_content = """
llm:
  default_provider: mock
  failover_chain:
    - mock
guardrails:
  max_duplicate_calls: 3
  max_output_chars: 8000
  per_turn_tool_limit: 30
trajectory:
  enabled: true
  directory: {traj_dir}
security:
  allowed_paths: []
  blocked_patterns:
    - /etc/
    - /root/.ssh/
""".format(traj_dir=str(tmp_path / "trajectories"))

    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_content, encoding="utf-8")
    return CktClawConfig(config_path=config_path)
