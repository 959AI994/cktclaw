"""
Task Manager - 任务生命周期管理器

参考 src/tasks/ 实现 Python 版本的任务管理系统。

核心职责：
1. 任务注册与查询
2. 任务状态转换（pending -> running -> completed/failed/killed）
3. 任务输出管理
4. 任务清理与终止

设计原则：
- 线程安全（asyncio.Lock）
- 状态机严格（防止非法状态转换）
- 输出持久化（文件系统）
- 资源清理（终止状态自动清理）
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
    """任务不存在错误"""
    pass


class TaskStateError(Exception):
    """任务状态错误"""
    pass


class TaskManager:
    """
    任务生命周期管理器（单例模式）

    管理所有任务的创建、状态转换、输出、清理
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
        """获取所有任务（只读）"""
        return self._tasks.copy()

    async def create_task(
        self,
        task_type: TaskType,
        description: str,
        tool_use_id: Optional[str] = None,
    ) -> TaskHandle:
        """
        创建新任务

        Args:
            task_type: 任务类型
            description: 任务描述
            tool_use_id: 工具使用 ID（可选）

        Returns:
            TaskHandle 包含任务 ID 和清理函数
        """
        async with self._task_lock:
            # 生成任务 ID
            task_id = generate_task_id(task_type)

            # 创建任务状态
            task_state = create_task_state_base(
                task_id=task_id,
                task_type=task_type,
                description=description,
                tool_use_id=tool_use_id,
            )

            # 注册任务
            self._tasks[task_id] = task_state

            # 创建输出文件
            os.makedirs(os.path.dirname(task_state.output_file), exist_ok=True)
            with open(task_state.output_file, "w") as f:
                f.write(f"Task {task_id} created at {datetime.now().isoformat()}\n")
                f.write(f"Description: {description}\n")
                f.write("-" * 70 + "\n")

            return TaskHandle(task_id=task_id)

    async def get_task(self, task_id: str) -> TaskStateBase:
        """
        获取任务状态

        Args:
            task_id: 任务 ID

        Returns:
            TaskStateBase 实例

        Raises:
            TaskNotFoundError: 任务不存在
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
        更新任务状态

        Args:
            task_id: 任务 ID
            status: 新状态
            end_time: 结束时间（可选）

        Raises:
            TaskNotFoundError: 任务不存在
            TaskStateError: 非法状态转换
        """
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task {task_id} not found")

            # 验证状态转换
            if is_terminal_task_status(task.status):
                raise TaskStateError(
                    f"Cannot update task {task_id} in terminal state {task.status}"
                )

            # 更新状态
            task.status = status

            # 如果是终止状态，记录结束时间
            if is_terminal_task_status(status):
                task.end_time = end_time or datetime.now().timestamp()

                # 写入输出文件
                with open(task.output_file, "a") as f:
                    f.write("-" * 70 + "\n")
                    f.write(f"Task {status.value} at {datetime.fromtimestamp(task.end_time).isoformat()}\n")

    async def append_task_output(
        self,
        task_id: str,
        output: str,
    ) -> None:
        """
        追加任务输出

        Args:
            task_id: 任务 ID
            output: 输出内容

        Raises:
            TaskNotFoundError: 任务不存在
        """
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task {task_id} not found")

            # 追加到输出文件
            with open(task.output_file, "a") as f:
                f.write(output)

            # 更新偏移量
            task.output_offset = os.path.getsize(task.output_file)

    async def read_task_output(
        self,
        task_id: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> str:
        """
        读取任务输出

        Args:
            task_id: 任务 ID
            offset: 起始偏移量（字节）
            limit: 最大读取字节数

        Returns:
            输出内容

        Raises:
            TaskNotFoundError: 任务不存在
        """
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task {task_id} not found")

            # 读取输出文件
            with open(task.output_file, "r") as f:
                if offset is not None:
                    f.seek(offset)
                if limit is not None:
                    return f.read(limit)
                return f.read()

    async def mark_task_notified(self, task_id: str) -> None:
        """
        标记任务已通知

        Args:
            task_id: 任务 ID

        Raises:
            TaskNotFoundError: 任务不存在
        """
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task {task_id} not found")
            task.notified = True

    async def kill_task(self, task_id: str) -> None:
        """
        终止任务

        Args:
            task_id: 任务 ID

        Raises:
            TaskNotFoundError: 任务不存在
            TaskStateError: 任务不在运行状态
        """
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(f"Task {task_id} not found")

            if task.status != TaskStatus.RUNNING:
                raise TaskStateError(
                    f"Cannot kill task {task_id} in state {task.status}"
                )

            # 执行清理函数
            cleanup = self._cleanup_handlers.get(task_id)
            if cleanup:
                cleanup()
                del self._cleanup_handlers[task_id]

            # 更新状态
            task.status = TaskStatus.KILLED
            task.end_time = datetime.now().timestamp()

            # 写入输出文件
            with open(task.output_file, "a") as f:
                f.write("-" * 70 + "\n")
                f.write(f"Task killed at {datetime.fromtimestamp(task.end_time).isoformat()}\n")

    async def register_cleanup_handler(
        self,
        task_id: str,
        cleanup: Callable[[], None],
    ) -> None:
        """
        注册任务清理函数

        Args:
            task_id: 任务 ID
            cleanup: 清理函数

        Raises:
            TaskNotFoundError: 任务不存在
        """
        async with self._task_lock:
            if task_id not in self._tasks:
                raise TaskNotFoundError(f"Task {task_id} not found")
            self._cleanup_handlers[task_id] = cleanup

    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None,
    ) -> List[TaskStateBase]:
        """
        列出任务

        Args:
            status: 过滤状态（可选）
            task_type: 过滤类型（可选）

        Returns:
            任务列表
        """
        async with self._task_lock:
            tasks = list(self._tasks.values())

            if status is not None:
                tasks = [t for t in tasks if t.status == status]

            if task_type is not None:
                tasks = [t for t in tasks if t.type == task_type]

            return [t.copy() for t in tasks]

    async def get_background_tasks(self) -> List[TaskStateBase]:
        """
        获取后台任务

        后台任务定义：
        1. 状态为 running 或 pending
        2. 未被标记为前台任务
        """
        async with self._task_lock:
            background_tasks = []
            for task in self._tasks.values():
                if task.status in (TaskStatus.RUNNING, TaskStatus.PENDING):
                    background_tasks.append(task.copy())
            return background_tasks

    async def cleanup_terminal_tasks(self, max_age_seconds: float = 3600) -> int:
        """
        清理终止状态的任务

        Args:
            max_age_seconds: 最大保留时间（秒）

        Returns:
            清理的任务数量
        """
        async with self._task_lock:
            now = datetime.now().timestamp()
            to_remove = []

            for task_id, task in self._tasks.items():
                if is_terminal_task_status(task.status):
                    if task.end_time and (now - task.end_time) > max_age_seconds:
                        to_remove.append(task_id)

            # 删除任务
            for task_id in to_remove:
                del self._tasks[task_id]
                # 删除清理函数
                if task_id in self._cleanup_handlers:
                    del self._cleanup_handlers[task_id]

            return len(to_remove)

    async def get_stats(self) -> Dict[str, Any]:
        """
        获取任务统计信息

        Returns:
            统计信息字典
        """
        async with self._task_lock:
            stats = {
                "total_tasks": len(self._tasks),
                "by_status": {},
                "by_type": {},
            }

            for task in self._tasks.values():
                # 按状态统计（Pydantic use_enum_values=True 已转为字符串）
                status_key = task.status if isinstance(task.status, str) else task.status.value
                stats["by_status"][status_key] = stats["by_status"].get(status_key, 0) + 1

                # 按类型统计
                type_key = task.type if isinstance(task.type, str) else task.type.value
                stats["by_type"][type_key] = stats["by_type"].get(type_key, 0) + 1

            return stats

    def reset(self) -> None:
        """重置任务管理器（仅用于测试）"""
        self._tasks.clear()
        self._cleanup_handlers.clear()


# 全局单例
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """获取全局任务管理器单例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
