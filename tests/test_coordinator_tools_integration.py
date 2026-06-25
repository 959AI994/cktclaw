"""Integration tests for coordinator Agent/SendMessage/TaskStop tools."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from cktclaw.agents.runtime import AgentRuntime
from cktclaw.agents.worker import WorkerAgent
from cktclaw.tools.agent.coordinator_tools import SendMessageTool, SpawnAgentTool, TaskStopTool
from cktclaw.tools.base import ToolContext


@pytest.fixture
def runtime():
    return AgentRuntime(max_concurrent=5)


def test_spawn_agent_tool_unknown_role():
    async def _run():
        tool = SpawnAgentTool()
        ctx = ToolContext(session_id="test")
        return await tool.execute(
            {"subagent_type": "nonexistent_agent", "task": "do something"},
            ctx,
        )

    result = asyncio.run(_run())
    assert not result.success


def test_spawn_agent_tool_spawns_worker(runtime):
    async def _run():
        tool = SpawnAgentTool()
        ctx = ToolContext(session_id="test")
        with patch("cktclaw.agents.runtime.get_agent_runtime", return_value=runtime):
            with patch.object(WorkerAgent, "run", new_callable=AsyncMock, return_value="done"):
                return await tool.execute(
                    {"subagent_type": "optimizer_agent", "task": "analyze bottlenecks"},
                    ctx,
                )

    result = asyncio.run(_run())
    assert result.success
    assert "agent_id" in (result.metadata or {})


def test_send_message_requires_worker_agent():
    async def _run():
        tool = SendMessageTool()
        ctx = ToolContext(session_id="test")
        runtime = AgentRuntime()
        with patch("cktclaw.agents.runtime.get_agent_runtime", return_value=runtime):
            return await tool.execute(
                {"agent_id": "missing", "message": "continue"},
                ctx,
            )

    result = asyncio.run(_run())
    assert not result.success


def test_task_stop_agent(runtime):
    async def _run():
        tool = TaskStopTool()
        ctx = ToolContext(session_id="test")
        agent = WorkerAgent(name="t", system_prompt="test")
        runtime._agents[agent.agent_id] = agent
        with patch("cktclaw.agents.runtime.get_agent_runtime", return_value=runtime):
            return await tool.execute({"agent_id": agent.agent_id}, ctx)

    result = asyncio.run(_run())
    assert result.success
