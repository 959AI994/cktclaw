"""
Agent Protocol — typed messages and events for inter-agent communication.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(str, Enum):
    """Agent lifecycle events."""
    SPAWNED = "spawned"
    STARTED = "started"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    MESSAGE = "message"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"
    BUDGET_EXCEEDED = "budget_exceeded"


@dataclass
class AgentMessage:
    """A message between agents."""
    from_agent: str  # agent_id of sender
    to_agent: str  # agent_id of receiver (or "coordinator")
    content: str
    message_type: str = "text"  # text, tool_result, status
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AgentEvent:
    """An event emitted during agent lifecycle."""
    agent_id: str
    event_type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_notification(self) -> str:
        """Format as notification string for coordinator."""
        if self.event_type == EventType.COMPLETED:
            return (
                f"<task-notification>\n"
                f"<task-id>{self.agent_id}</task-id>\n"
                f"<status>completed</status>\n"
                f"<summary>{self.data.get('summary', 'Task completed')}</summary>\n"
                f"<result>{self.data.get('result', '')}</result>\n"
                f"</task-notification>"
            )
        elif self.event_type == EventType.FAILED:
            return (
                f"<task-notification>\n"
                f"<task-id>{self.agent_id}</task-id>\n"
                f"<status>failed</status>\n"
                f"<summary>{self.data.get('error', 'Task failed')}</summary>\n"
                f"</task-notification>"
            )
        return f"[Agent {self.agent_id}] {self.event_type.value}: {self.data}"
