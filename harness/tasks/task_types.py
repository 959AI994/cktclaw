"""
Task Types - 任务状态类型定义

参考 src/Task.ts 实现 Python 版本的任务类型系统。

核心职责：
1. 定义任务类型枚举（TaskType）
2. 定义任务状态枚举（TaskStatus）
3. 定义任务状态基类（TaskStateBase）
4. 提供任务 ID 生成器
5. 提供任务状态判断函数

设计原则：
- 类型安全（使用 Enum）
- 状态机清晰（pending -> running -> completed/failed/killed）
- ID 生成安全（使用随机字节）
"""

import os
import secrets
from enum import Enum
from typing import Optional, Callable, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TaskType(str, Enum):
    """任务类型"""
    LOCAL_BASH = "local_bash"
    LOCAL_AGENT = "local_agent"
    REMOTE_AGENT = "remote_agent"
    IN_PROCESS_TEAMMATE = "in_process_teammate"
    LOCAL_WORKFLOW = "local_workflow"
    MONITOR_MCP = "monitor_mcp"
    DREAM = "dream"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


def is_terminal_task_status(status: TaskStatus) -> bool:
    """
    判断任务是否处于终止状态

    终止状态：completed, failed, killed
    用于防止向已终止的任务注入消息、清理任务等
    """
    return status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.KILLED)


class TaskHandle(BaseModel):
    """任务句柄"""
    task_id: str
    cleanup: Optional[Callable[[], None]] = None


class TaskStateBase(BaseModel):
    """
    任务状态基类

    所有具体任务类型的共享字段
    """
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


# Task ID 前缀映射
TASK_ID_PREFIXES = {
    TaskType.LOCAL_BASH: "b",
    TaskType.LOCAL_AGENT: "a",
    TaskType.REMOTE_AGENT: "r",
    TaskType.IN_PROCESS_TEAMMATE: "t",
    TaskType.LOCAL_WORKFLOW: "w",
    TaskType.MONITOR_MCP: "m",
    TaskType.DREAM: "d",
}

# 任务 ID 字母表（36 进制，不区分大小写）
# 36^8 ≈ 2.8 万亿组合，足以抵抗暴力攻击
TASK_ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def get_task_id_prefix(task_type: TaskType) -> str:
    """获取任务 ID 前缀"""
    return TASK_ID_PREFIXES.get(task_type, "x")


def generate_task_id(task_type: TaskType) -> str:
    """
    生成任务 ID

    格式：<prefix><8位随机字符>
    例如：b3a7f2e1, a9c4d8b2
    """
    prefix = get_task_id_prefix(task_type)
    random_bytes = secrets.token_bytes(8)

    task_id = prefix
    for byte in random_bytes:
        task_id += TASK_ID_ALPHABET[byte % len(TASK_ID_ALPHABET)]

    return task_id


def get_task_output_path(task_id: str) -> str:
    """
    获取任务输出文件路径

    参考 src/utils/task/diskOutput.ts
    """
    # 使用临时目录存储任务输出
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
    创建任务状态基类实例

    Args:
        task_id: 任务 ID
        task_type: 任务类型
        description: 任务描述
        tool_use_id: 工具使用 ID（可选）

    Returns:
        TaskStateBase 实例
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
