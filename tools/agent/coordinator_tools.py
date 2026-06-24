"""
Coordinator tools — Agent / SendMessage / TaskStop bridged to AgentRuntime.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class SpawnAgentTool(BaseTool):
    name = "Agent"
    description = (
        "Spawn a specialist sub-agent from the CktClaw seven-agent roster. "
        "Use subagent_type as role_id: pm_agent, architect_agent, eda_agent, "
        "compiler_agent, runtime_agent, deploy_agent, optimizer_agent."
    )
    parameters = {
        "type": "object",
        "properties": {
            "subagent_type": {
                "type": "string",
                "description": "Roster role_id (e.g. architect_agent, eda_agent).",
            },
            "task": {
                "type": "string",
                "description": "Task description for the sub-agent.",
            },
            "name": {
                "type": "string",
                "description": "Optional display name override.",
            },
        },
        "required": ["subagent_type", "task"],
    }
    read_only = True
    category = "agent"

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        from ...agents.runtime import get_agent_runtime
        from ...agents.roster_registry import get_roster, _normalize_role_id

        role_id = _normalize_role_id(params.get("subagent_type") or params.get("name") or "")
        task = params.get("task", "")
        if not task:
            return ToolResult.fail("Parameter 'task' is required.")

        if get_roster().get(role_id) is None:
            return ToolResult.fail(f"Unknown subagent_type: {role_id}")

        runtime = get_agent_runtime()
        try:
            agent_id = await runtime.spawn_specialist(
                role_id,
                task,
                context={"session_id": context.session_id, "working_dir": context.working_dir},
            )
            return ToolResult.ok(
                output=f"Spawned agent {agent_id} ({role_id}). Await task-notification when complete.",
                metadata={"agent_id": agent_id, "role_id": role_id},
            )
        except Exception as e:
            return ToolResult.fail(str(e))


class SendMessageTool(BaseTool):
    name = "SendMessage"
    description = "Send a follow-up message to an existing sub-agent and continue its session."
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "Target agent id."},
            "message": {"type": "string", "description": "Follow-up instruction."},
        },
        "required": ["agent_id", "message"],
    }
    read_only = True
    category = "agent"

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        from ...agents.runtime import get_agent_runtime
        from ...agents.worker import WorkerAgent

        agent_id = params.get("agent_id", "")
        message = params.get("message", "")
        if not agent_id or not message:
            return ToolResult.fail("agent_id and message are required.")

        runtime = get_agent_runtime()
        agent = runtime.get_agent(agent_id)
        if agent is None:
            return ToolResult.fail(f"Agent not found: {agent_id}")

        if not isinstance(agent, WorkerAgent):
            return ToolResult.fail(
                f"Agent {agent_id} does not support SendMessage (meta/orchestrator agent)."
            )

        try:
            result = await agent.continue_conversation(message)
            return ToolResult.ok(output=result or "(no output)", metadata={"agent_id": agent_id})
        except Exception as e:
            return ToolResult.fail(str(e))


class TaskStopTool(BaseTool):
    name = "TaskStop"
    description = "Stop a running sub-agent."
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "Agent id to stop."},
            "reason": {"type": "string", "description": "Optional stop reason."},
        },
        "required": ["agent_id"],
    }
    read_only = True
    category = "agent"

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        from ...agents.runtime import get_agent_runtime

        agent_id = params.get("agent_id", "")
        if not agent_id:
            return ToolResult.fail("agent_id is required.")

        runtime = get_agent_runtime()
        ok = await runtime.stop_agent(agent_id, params.get("reason") or "Stopped via TaskStop")
        if ok:
            return ToolResult.ok(output=f"Agent {agent_id} stopped.")
        return ToolResult.fail(f"Agent not found or already stopped: {agent_id}")
