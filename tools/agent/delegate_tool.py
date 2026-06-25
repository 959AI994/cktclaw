"""
Delegate Tool — allows LLM to spawn sub-agents autonomously.

The LLM can use this tool to delegate complex sub-tasks to a fresh
WorkerAgent with its own budget and optional tool subset.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class DelegateTaskTool(BaseTool):
    """
    Tool that spawns a sub-agent to handle a delegated task.

    The parent LLM can use this when a sub-task is complex enough
    to warrant its own conversation loop with independent budget.
    """

    name = "delegate_task"
    description = (
        "Delegate a sub-task to an autonomous agent. Use when a task is complex, "
        "requires multiple tool calls, or would benefit from focused attention. "
        "The sub-agent runs independently with its own tool access and budget, "
        "then returns the result."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": (
                    "Clear, detailed description of the task for the sub-agent. "
                    "Include all necessary context and expected output format."
                ),
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of specific tool names the sub-agent should use. "
                    "If not provided, all available tools are accessible."
                ),
            },
            "max_turns": {
                "type": "integer",
                "description": "Maximum LLM turns for the sub-agent (default: 10).",
            },
            "model": {
                "type": "string",
                "description": (
                    "LLM provider to use (deepseek/claude/openai). "
                    "Defaults to current provider."
                ),
            },
        },
        "required": ["task"],
    }
    read_only = True  # The tool itself is read-only; sub-agent may mutate
    category = "agent"

    # Sub-agent limits (prevent unbounded recursion)
    MAX_SUB_AGENT_TURNS = 20
    MAX_SUB_AGENT_TOKENS = 50_000
    MAX_SUB_AGENT_TOOL_CALLS = 30

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """Spawn a sub-agent and return its result."""
        task = params.get("task", "")
        if not task:
            return ToolResult.fail("Parameter 'task' is required and cannot be empty.")

        allowed_tools = params.get("tools")
        max_turns = min(params.get("max_turns", 10), self.MAX_SUB_AGENT_TURNS)
        model = params.get("model", "")

        try:
            from ...agents.worker import WorkerAgent
            from ...agents.base import AgentBudget

            budget = AgentBudget(
                max_turns=max_turns,
                max_tokens=self.MAX_SUB_AGENT_TOKENS,
                max_tool_calls=self.MAX_SUB_AGENT_TOOL_CALLS,
            )

            agent = WorkerAgent(
                name=f"sub-agent-{context.session_id[:8]}",
                system_prompt=(
                    "You are a focused sub-agent. Complete the delegated task "
                    "efficiently using available tools. Return a clear, concise result."
                ),
                budget=budget,
                allowed_tools=allowed_tools,
                model=model or "deepseek",
            )

            logger.info(f"Spawning sub-agent for task: {task[:100]}...")
            result = await agent.run(task)

            if agent.status.value == "completed":
                return ToolResult.ok(
                    output=result or "(Sub-agent completed with no output)",
                    metadata={
                        "agent_id": agent.agent_id,
                        "turns_used": agent.budget.turns_used,
                        "tokens_used": agent.budget.tokens_used,
                        "status": agent.status.value,
                    },
                )
            else:
                return ToolResult.fail(
                    error=f"Sub-agent ended with status: {agent.status.value}. "
                          f"Error: {agent.error or 'unknown'}",
                    output=result or "",
                    metadata={
                        "agent_id": agent.agent_id,
                        "status": agent.status.value,
                    },
                )

        except ImportError as e:
            return ToolResult.fail(f"Agent system not available: {e}")
        except Exception as e:
            logger.exception("Sub-agent execution failed")
            return ToolResult.fail(f"Delegation failed: {str(e)}")
