"""
BaseAgent — abstract agent with lifecycle, budget, and tool sandbox.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .protocol import AgentEvent, AgentMessage, EventType


class AgentStatus(str, Enum):
    """Agent lifecycle states."""
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"  # Waiting for tool result
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"
    BUDGET_EXCEEDED = "budget_exceeded"


@dataclass
class AgentBudget:
    """Resource limits for an agent."""
    max_turns: int = 20
    max_tokens: int = 100_000  # Total tokens (input + output)
    timeout_seconds: int = 300  # 5 minutes
    max_tool_calls: int = 50
    allowed_tools: Optional[List[str]] = None  # None = all tools

    # Tracking (mutable)
    turns_used: int = 0
    tokens_used: int = 0
    tool_calls_used: int = 0
    started_at: Optional[str] = None

    def is_exceeded(self) -> Optional[str]:
        """Check if any budget limit is exceeded. Returns reason or None."""
        if self.turns_used >= self.max_turns:
            return f"max_turns ({self.max_turns})"
        if self.tokens_used >= self.max_tokens:
            return f"max_tokens ({self.max_tokens})"
        if self.tool_calls_used >= self.max_tool_calls:
            return f"max_tool_calls ({self.max_tool_calls})"
        if self.started_at:
            elapsed = (
                datetime.now() - datetime.fromisoformat(self.started_at)
            ).total_seconds()
            if elapsed >= self.timeout_seconds:
                return f"timeout ({self.timeout_seconds}s)"
        return None

    def record_turn(self, tokens: int = 0, tool_calls: int = 0) -> None:
        """Record resource usage for one turn."""
        self.turns_used += 1
        self.tokens_used += tokens
        self.tool_calls_used += tool_calls


@dataclass
class AgentState:
    """Serializable state of an agent (for checkpoint/resume)."""
    agent_id: str
    name: str
    status: AgentStatus
    messages: List[Dict[str, Any]] = field(default_factory=list)
    budget: Optional[AgentBudget] = None
    result: str = ""
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """
    Abstract base class for CktClaw agents.

    Agents execute tasks autonomously using LLM + tools within budget limits.
    """

    def __init__(
        self,
        name: str,
        system_prompt: str = "",
        budget: Optional[AgentBudget] = None,
        agent_id: Optional[str] = None,
    ):
        self.agent_id = agent_id or f"agent-{uuid.uuid4().hex[:8]}"
        self.name = name
        self.system_prompt = system_prompt
        self.budget = budget or AgentBudget()
        self.status = AgentStatus.CREATED
        self.result = ""
        self.error = ""
        self._event_listeners: List[Callable[[AgentEvent], None]] = []
        self._messages: List[Dict[str, Any]] = []

    def on_event(self, listener: Callable[[AgentEvent], None]) -> None:
        """Register an event listener."""
        self._event_listeners.append(listener)

    def _emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an event to all listeners."""
        event = AgentEvent(
            agent_id=self.agent_id,
            event_type=event_type,
            data=data or {},
        )
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception:
                pass

    @abstractmethod
    async def run(self, initial_message: str) -> str:
        """
        Execute the agent's task.

        Args:
            initial_message: The task description / first user message.

        Returns:
            The agent's final output/result string.
        """
        ...

    async def stop(self, reason: str = "User requested") -> None:
        """Stop the agent."""
        self.status = AgentStatus.KILLED
        self.error = reason
        self._emit(EventType.KILLED, {"reason": reason})

    def get_state(self) -> AgentState:
        """Get serializable agent state for checkpoint."""
        return AgentState(
            agent_id=self.agent_id,
            name=self.name,
            status=self.status,
            messages=list(self._messages),
            budget=self.budget,
            result=self.result,
            error=self.error,
        )
