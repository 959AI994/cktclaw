"""
AgentRuntime — manages concurrent agent execution.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from .base import BaseAgent, AgentBudget, AgentStatus
from .protocol import AgentEvent, AgentMessage, EventType
from .worker import WorkerAgent

logger = logging.getLogger(__name__)


class AgentRuntime:
    """
    Manages a pool of running agents.

    Responsibilities:
    - Spawn new agents (worker, specialist)
    - Track running agents
    - Collect results
    - Enforce global resource limits
    - Emit events to coordinator
    """

    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self._agents: Dict[str, BaseAgent] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._event_listeners: List[Callable[[AgentEvent], None]] = []
        self._results: Dict[str, str] = {}

    def on_event(self, listener: Callable[[AgentEvent], None]) -> None:
        """Register a global event listener for all agents."""
        self._event_listeners.append(listener)

    def _broadcast_event(self, event: AgentEvent) -> None:
        """Broadcast agent event to all global listeners."""
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception as e:
                logger.debug(f"Event listener error: {e}")

    async def spawn_worker(
        self,
        name: str,
        task: str,
        system_prompt: str = "",
        allowed_tools: Optional[List[str]] = None,
        model: str = "deepseek",
        budget: Optional[AgentBudget] = None,
    ) -> str:
        """
        Spawn a new worker agent.

        Args:
            name: Human-readable name for the worker.
            task: The task/message to execute.
            system_prompt: System prompt for the worker.
            allowed_tools: Tool whitelist (None = all).
            model: LLM provider to use.
            budget: Resource limits.

        Returns:
            agent_id of the spawned worker.
        """
        if len(self._tasks) >= self.max_concurrent:
            # Find completed tasks to clean up
            self._cleanup_completed()
            if len(self._tasks) >= self.max_concurrent:
                raise RuntimeError(
                    f"Max concurrent agents ({self.max_concurrent}) reached"
                )

        if not system_prompt:
            system_prompt = (
                "You are a CktClaw worker agent specialized in EDA tasks. "
                "Execute the given task using available tools. "
                "Be concise and focused. Report your results clearly."
            )

        agent = WorkerAgent(
            name=name,
            system_prompt=system_prompt,
            budget=budget or AgentBudget(),
            allowed_tools=allowed_tools,
            model=model,
        )

        # Register event forwarding
        agent.on_event(self._broadcast_event)

        self._agents[agent.agent_id] = agent
        self._broadcast_event(AgentEvent(
            agent_id=agent.agent_id,
            event_type=EventType.SPAWNED,
            data={"name": name, "task": task[:200]},
        ))

        # Launch as async task
        async_task = asyncio.create_task(self._run_agent(agent, task))
        self._tasks[agent.agent_id] = async_task

        return agent.agent_id

    async def _run_agent(self, agent: BaseAgent, task: str) -> None:
        """Run an agent and store its result."""
        try:
            result = await agent.run(task)
            self._results[agent.agent_id] = result
        except Exception as e:
            agent.status = AgentStatus.FAILED
            agent.error = str(e)
            self._results[agent.agent_id] = ""
            logger.error(f"Agent {agent.agent_id} crashed: {e}")

    async def wait_for(self, agent_id: str, timeout: float = 300) -> Optional[str]:
        """Wait for an agent to complete and return its result."""
        task = self._tasks.get(agent_id)
        if not task:
            return self._results.get(agent_id)

        try:
            await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            agent = self._agents.get(agent_id)
            if agent:
                await agent.stop("Timeout")
            return None

        return self._results.get(agent_id, "")

    async def stop_agent(self, agent_id: str, reason: str = "User requested") -> bool:
        """Stop a running agent."""
        agent = self._agents.get(agent_id)
        if not agent:
            return False

        await agent.stop(reason)

        task = self._tasks.get(agent_id)
        if task and not task.done():
            task.cancel()

        return True

    def get_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of an agent."""
        agent = self._agents.get(agent_id)
        if not agent:
            return None

        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "status": agent.status.value,
            "result": agent.result[:500] if agent.result else "",
            "error": agent.error,
            "budget": {
                "turns": f"{agent.budget.turns_used}/{agent.budget.max_turns}",
                "tokens": f"{agent.budget.tokens_used}/{agent.budget.max_tokens}",
            },
        }

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all agents with their status."""
        return [
            self.get_status(aid) for aid in self._agents
            if self.get_status(aid) is not None
        ]

    def _cleanup_completed(self) -> None:
        """Remove completed/failed tasks from the active pool."""
        done_ids = [
            aid for aid, task in self._tasks.items()
            if task.done()
        ]
        for aid in done_ids:
            del self._tasks[aid]

    async def stop_all(self) -> None:
        """Stop all running agents."""
        for agent_id in list(self._tasks.keys()):
            await self.stop_agent(agent_id, "Shutdown")


# Global singleton
_agent_runtime: Optional[AgentRuntime] = None


def get_agent_runtime() -> AgentRuntime:
    """Get or create the global AgentRuntime."""
    global _agent_runtime
    if _agent_runtime is None:
        _agent_runtime = AgentRuntime()
    return _agent_runtime
