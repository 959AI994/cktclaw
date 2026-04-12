"""
Task types — enums, IDs, and shared fields for background work.

Covers:
1. TaskType discriminator
2. TaskStatus lifecycle values
3. TaskStateBase shared columns
4. Secure-ish random task id generator
5. Helpers such as is_terminal_task_status

Principles:
- Prefer Enum for wire-stable values
- Lifecycle: pending -> running -> terminal states
- IDs mix type prefix + randomness (not cryptographic)
"""

import os
import secrets
from enum import Enum
from typing import Optional, Callable, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TaskType(str, Enum):
    """Concrete background job kinds."""
    LOCAL_BASH = "local_bash"
    LOCAL_AGENT = "local_agent"
    REMOTE_AGENT = "remote_agent"
    IN_PROCESS_TEAMMATE = "in_process_teammate"
    LOCAL_WORKFLOW = "local_workflow"
    MONITOR_MCP = "monitor_mcp"
    DREAM = "dream"


class TaskStatus(str, Enum):
    """Lifecycle flags for a TaskHandle."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


def is_terminal_task_status(status: TaskStatus) -> bool:
    """
    Return True when no further messages should target this task.

    Terminal == completed, failed, or killed (cleanup / GC helpers).
    """
    return status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.KILLED)


class TaskHandle(BaseModel):
    """Lightweight reference to a running background task."""
    task_id: str
    cleanup: Optional[Callable[[], None]] = None


class TaskStateBase(BaseModel):
    """Shared columns for every concrete task state model."""
    id: str
    type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    description: str
    tool_use_id: Optional[str] = None
    start_time: float = Field(default_factory=lambda: datetime.now().timestamp())
    end_time: Optional[float] = None
    total_paused_ms: Optional[float] = None
    output_file: str
    output_offset: int = 0
    notified: bool = False

    class Config:
        arbitrary_types_allowed = True
        use_enum_values = True


# Prefix letters encode task family for log readability
TASK_ID_PREFIXES = {
    TaskType.LOCAL_BASH: "b",
    TaskType.LOCAL_AGENT: "a",
    TaskType.REMOTE_AGENT: "r",
    TaskType.IN_PROCESS_TEAMMATE: "t",
    TaskType.LOCAL_WORKFLOW: "w",
    TaskType.MONITOR_MCP: "m",
    TaskType.DREAM: "d",
}

# 36-character alphabet for suffix randomness (not a security boundary)
TASK_ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def get_task_id_prefix(task_type: TaskType) -> str:
    """Return the single-letter prefix for a task type."""
    return TASK_ID_PREFIXES.get(task_type, "x")


def generate_task_id(task_type: TaskType) -> str:
    """
    Build `<prefix><8 random chars>` identifiers (base-36 digits).
    """
    prefix = get_task_id_prefix(task_type)
    random_bytes = secrets.token_bytes(8)

    task_id = prefix
    for byte in random_bytes:
        task_id += TASK_ID_ALPHABET[byte % len(TASK_ID_ALPHABET)]

    return task_id


def get_task_output_path(task_id: str) -> str:
    """Return ~/.cktclaw/tasks/<task_id>.txt for streaming logs."""
    temp_dir = os.path.join(os.path.expanduser("~"), ".cktclaw", "tasks")
    os.makedirs(temp_dir, exist_ok=True)
    return os.path.join(temp_dir, f"{task_id}.txt")


def create_task_state_base(
    task_id: str,
    task_type: TaskType,
    description: str,
    tool_use_id: Optional[str] = None,
) -> TaskStateBase:
    """
    Factory for a pending TaskStateBase row.

    Args:
        task_id: Stable task identifier.
        task_type: TaskType discriminator.
        description: Human-readable summary.
        tool_use_id: Optional originating tool_use id.

    Returns:
        Fresh TaskStateBase in PENDING status.
    """
    return TaskStateBase(
        id=task_id,
        type=task_type,
        status=TaskStatus.PENDING,
        description=description,
        tool_use_id=tool_use_id,
        start_time=datetime.now().timestamp(),
        output_file=get_task_output_path(task_id),
        output_offset=0,
        notified=False,
    )
