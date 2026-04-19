"""
Task manager — lifecycle, log files, and cleanup for background jobs.

Responsibilities:
1. Register tasks and expose read-only snapshots
2. Enforce pending -> running -> terminal transitions
3. Stream stdout-style logs to per-task files
4. Run optional cleanup hooks when tasks are killed

Design:
- asyncio.Lock protects the in-memory tables
- Illegal transitions raise TaskStateError
- Output persists under ~/.cktclaw/tasks/<id>.txt
- Terminal rows can be aged out via cleanup_terminal_tasks
"""

import asyncio
import os
from typing import Dict, Optional, List, Callable, Any
from datetime import datetime

from .task_types import (
    TaskType,
    TaskStatus,
    TaskStateBase,
    TaskHandle,
    is_terminal_task_status,
    generate_task_id,
    create_task_state_base,
)


class TaskNotFoundError(Exception):
    """Raised when a task id is unknown."""
    pass


class TaskStateError(Exception):
    """Raised when a state transition violates the task lifecycle."""
    pass


class TaskManager:
    """
    Singleton registry for TaskStateBase rows.

    Owns handles, log offsets, and optional cleanup callbacks.
    """

    _instance: Optional['TaskManager'] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tasks: Dict[str, TaskStateBase] = {}
            cls._instance._task_lock = asyncio.Lock()
            cls._instance._cleanup_handlers: Dict[str, Callable[[], None]] = {}
        return cls._instance

    @property
    def tasks(self) -> Dict[str, TaskStateBase]:
        """Shallow copy of active tasks (read-only consumers)."""
        return self._tasks.copy()

    async def create_task(
        self,
        task_type: TaskType,
        description: str,
        tool_use_id: Optional[str] = None,
    ) -> TaskHandle:
        """
        Allocate a new task id, seed its log file, and return a handle.

        Args:
            task_type: Discriminator for logging / policy.
            description: Human-readable summary for the header block.
            tool_use_id: Optional originating tool_use id.

        Returns:
            TaskHandle carrying the generated id (cleanup wired later).
        """
        async with self._task_lock:
            task_id = generate_task_id(task_type)

            task_state = create_task_state_base(
                task_id=task_id,
                task_type=task_type,
                description=description,
                tool_use_id=tool_use_id,
            )

            self._tasks[task_id] = task_state

            os.makedirs(os.path.dirname(task_state.output_file), exist_ok=True)
            with open(task_state.output_file, "w") as f:
                f.write(f"Task {task_id} created at {datetime.now().isoformat()}\n")
                f.write(f"Description: {description}\n")
                f.write("-" * 70 + "\n")

            return TaskHandle(task_id=task_id)

    async def get_task(self, task_id: str) -> TaskStateBase:
        """
        Return a defensive copy of the task row.

        Raises:
            TaskNotFoundError: Unknown id.
        """
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task {task_id} not found")
            return task.copy()

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        end_time: Optional[float] = None,
    ) -> None:
        """
        Move a task along its lifecycle.

        Raises:
            TaskNotFoundError: Unknown id.
            TaskStateError: Task already terminal (unless setting same status).
        """
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task {task_id} not found")

            # Allow idempotent updates (setting same terminal status)
            if is_terminal_task_status(task.status):
                if task.status == status:
                    # Idempotent: already in this terminal state, no-op
                    return
                else:
                    raise TaskStateError(
                        f"Cannot update task {task_id} in terminal state {task.status}"
                    )

            task.status = status

            if is_terminal_task_status(status):
                task.end_time = end_time or datetime.now().timestamp()

                with open(task.output_file, "a") as f:
                    f.write("-" * 70 + "\n")
                    f.write(f"Task {status.value} at {datetime.fromtimestamp(task.end_time).isoformat()}\n")

    async def append_task_output(
        self,
        task_id: str,
        output: str,
    ) -> None:
        """Append UTF-8 text to the task log and refresh output_offset."""
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task {task_id} not found")

            with open(task.output_file, "a") as f:
                f.write(output)

            task.output_offset = os.path.getsize(task.output_file)

    async def append_output(
        self,
        task_id: str,
        output: str,
    ) -> None:
        """Append to the task log (alias for :meth:`append_task_output`, used by workflow skills)."""
        await self.append_task_output(task_id, output)

    async def read_task_output(
        self,
        task_id: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> str:
        """
        Read log tail or slice.

        Args:
            task_id: Target task.
            offset: Byte offset into the log file.
            limit: Max bytes to read (None == read remainder).
        """
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task {task_id} not found")

            with open(task.output_file, "r") as f:
                if offset is not None:
                    f.seek(offset)
                if limit is not None:
                    return f.read(limit)
                return f.read()

    async def mark_task_notified(self, task_id: str) -> None:
        """Flip notified=True after the UI surfaced completion."""
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task {task_id} not found")
            task.notified = True

    async def kill_task(self, task_id: str) -> None:
        """
        Force a RUNNING task into KILLED and invoke its cleanup hook.

        Raises:
            TaskNotFoundError: Unknown id.
            TaskStateError: Task not RUNNING.
        """
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task {task_id} not found")

            if task.status != TaskStatus.RUNNING:
                raise TaskStateError(
                    f"Cannot kill task {task_id} in state {task.status}"
                )

            cleanup = self._cleanup_handlers.get(task_id)
            if cleanup:
                cleanup()
                del self._cleanup_handlers[task_id]

            task.status = TaskStatus.KILLED
            task.end_time = datetime.now().timestamp()

            with open(task.output_file, "a") as f:
                f.write("-" * 70 + "\n")
                f.write(f"Task killed at {datetime.fromtimestamp(task.end_time).isoformat()}\n")

    async def register_cleanup_handler(
        self,
        task_id: str,
        cleanup: Callable[[], None],
    ) -> None:
        """Attach a synchronous cleanup callable (usually stops subprocesses)."""
        async with self._task_lock:
            if task_id not in self._tasks:
                raise TaskNotFoundError(f"Task {task_id} not found")
            self._cleanup_handlers[task_id] = cleanup

    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None,
    ) -> List[TaskStateBase]:
        """Enumerate tasks with optional filters."""
        async with self._task_lock:
            tasks = list(self._tasks.values())

            if status is not None:
                tasks = [t for t in tasks if t.status == status]

            if task_type is not None:
                tasks = [t for t in tasks if t.type == task_type]

            return [t.copy() for t in tasks]

    async def get_background_tasks(self) -> List[TaskStateBase]:
        """
        Tasks that still need UI attention (running or pending).

        Note: There is no separate foreground flag yet; this mirrors the
        legacy heuristic (active non-terminal work).
        """
        async with self._task_lock:
            background_tasks = []
            for task in self._tasks.values():
                if task.status in (TaskStatus.RUNNING, TaskStatus.PENDING):
                    background_tasks.append(task.copy())
            return background_tasks

    async def cleanup_terminal_tasks(self, max_age_seconds: float = 3600) -> int:
        """
        Drop terminal tasks older than ``max_age_seconds``.

        Returns:
            Number of tasks removed from memory.
        """
        async with self._task_lock:
            now = datetime.now().timestamp()
            to_remove = []

            for task_id, task in self._tasks.items():
                if is_terminal_task_status(task.status):
                    if task.end_time and (now - task.end_time) > max_age_seconds:
                        to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]
                if task_id in self._cleanup_handlers:
                    del self._cleanup_handlers[task_id]

            return len(to_remove)

    async def get_stats(self) -> Dict[str, Any]:
        """Lightweight histogram for dashboards."""
        async with self._task_lock:
            stats = {
                "total_tasks": len(self._tasks),
                "by_status": {},
                "by_type": {},
            }

            for task in self._tasks.values():
                # Pydantic may surface enum values as plain strings
                status_key = task.status if isinstance(task.status, str) else task.status.value
                stats["by_status"][status_key] = stats["by_status"].get(status_key, 0) + 1

                type_key = task.type if isinstance(task.type, str) else task.type.value
                stats["by_type"][type_key] = stats["by_type"].get(type_key, 0) + 1

            return stats

    def reset(self) -> None:
        """Wipe tables (unit tests only)."""
        self._tasks.clear()
        self._cleanup_handlers.clear()


_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """Lazy singleton accessor."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
