"""
Coordinator types — enums and payloads for multi-worker flows.

Includes:
1. Coordinator mode flags
2. Worker notification envelopes
3. Coordinator-scoped configuration

Principles:
- Coordinator vs worker roles stay isolated
- Tool allowlists differ per role
- Notifications use a stable structured wire format
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class CoordinatorMode(str, Enum):
    """High-level routing mode for the harness."""
    COORDINATOR = "coordinator"  # multi-worker coordinator
    NORMAL = "normal"            # single-agent REPL


class NotificationStatus(str, Enum):
    """Terminal states reported inside <task-notification>."""
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class WorkerUsage(BaseModel):
    """Token / tool / duration counters for a finished worker."""
    total_tokens: int = 0
    tool_uses: int = 0
    duration_ms: int = 0


class WorkerNotification(BaseModel):
    """Structured view of <task-notification> worker XML."""
    task_id: str
    status: NotificationStatus
    summary: str
    result: Optional[str] = None
    usage: Optional[WorkerUsage] = None
    created_at: datetime = Field(default_factory=datetime.now)


class CoordinatorConfig(BaseModel):
    """Mutable coordinator knobs (copied per read)."""
    mode: CoordinatorMode = CoordinatorMode.NORMAL

    worker_tools: List[str] = Field(default_factory=lambda: [
        "Bash",
        "Read",
        "Edit",
    ])

    coordinator_tools: List[str] = Field(default_factory=lambda: [
        "Agent",
        "SendMessage",
        "TaskStop",
    ])

    internal_tools: List[str] = Field(default_factory=lambda: [
        "TeamCreate",
        "TeamDelete",
        "SyntheticOutput",
    ])

    scratchpad_enabled: bool = False
    scratchpad_dir: Optional[str] = None

    mcp_servers: List[str] = Field(default_factory=list)


def parse_worker_notification(xml_content: str) -> Optional[WorkerNotification]:
    """
    Parse worker XML envelopes.

    Example:
    <task-notification>
    <task-id>agent-a1b</task-id>
    <status>completed</status>
    <summary>Agent completed</summary>
    <result>...</result>
    <usage>
      <total_tokens>1000</total_tokens>
      <tool_uses>5</tool_uses>
      <duration_ms>3000</duration_ms>
    </usage>
    </task-notification>
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_content)

        if root.tag != "task-notification":
            return None

        task_id = root.find("task-id")
        status = root.find("status")
        summary = root.find("summary")
        result = root.find("result")
        usage_elem = root.find("usage")

        if task_id is None or status is None or summary is None:
            return None

        usage = None
        if usage_elem is not None:
            total_tokens = usage_elem.find("total_tokens")
            tool_uses = usage_elem.find("tool_uses")
            duration_ms = usage_elem.find("duration_ms")

            usage = WorkerUsage(
                total_tokens=int(total_tokens.text) if total_tokens is not None else 0,
                tool_uses=int(tool_uses.text) if tool_uses is not None else 0,
                duration_ms=int(duration_ms.text) if duration_ms is not None else 0,
            )

        return WorkerNotification(
            task_id=task_id.text,
            status=NotificationStatus(status.text),
            summary=summary.text,
            result=result.text if result is not None else None,
            usage=usage,
        )
    except Exception:
        return None


def format_worker_notification(notification: WorkerNotification) -> str:
    """Serialize WorkerNotification back to XML (tests / debugging)."""
    lines = ["<task-notification>"]
    lines.append(f"<task-id>{notification.task_id}</task-id>")
    lines.append(f"<status>{notification.status.value}</status>")
    lines.append(f"<summary>{notification.summary}</summary>")

    if notification.result:
        lines.append(f"<result>{notification.result}</result>")

    if notification.usage:
        lines.append("<usage>")
        lines.append(f"  <total_tokens>{notification.usage.total_tokens}</total_tokens>")
        lines.append(f"  <tool_uses>{notification.usage.tool_uses}</tool_uses>")
        lines.append(f"  <duration_ms>{notification.usage.duration_ms}</duration_ms>")
        lines.append("</usage>")

    lines.append("</task-notification>")
    return "\n".join(lines)
