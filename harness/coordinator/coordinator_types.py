"""
Coordinator Types - 调度器类型定义

参考 src/coordinator/coordinatorMode.ts 实现 Python 版本的调度系统。

核心职责：
1. 定义 Coordinator 模式枚举
2. 定义 Worker 通知结构
3. 定义调度配置

设计原则：
- 模式隔离（Coordinator vs Worker）
- 工具隔离（不同角色有不同工具集）
- 通知标准化（XML 格式解析）
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class CoordinatorMode(str, Enum):
    """Coordinator 模式"""
    COORDINATOR = "coordinator"  # 调度模式
    NORMAL = "normal"            # 普通模式


class NotificationStatus(str, Enum):
    """Worker 通知状态"""
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class WorkerUsage(BaseModel):
    """Worker 使用统计"""
    total_tokens: int = 0
    tool_uses: int = 0
    duration_ms: int = 0


class WorkerNotification(BaseModel):
    """
    Worker 通知结构

    对应 <task-notification> XML 格式
    """
    task_id: str
    status: NotificationStatus
    summary: str
    result: Optional[str] = None
    usage: Optional[WorkerUsage] = None
    created_at: datetime = Field(default_factory=datetime.now)


class CoordinatorConfig(BaseModel):
    """Coordinator 配置"""
    # 模式配置
    mode: CoordinatorMode = CoordinatorMode.NORMAL

    # Worker 工具配置
    worker_tools: List[str] = Field(default_factory=lambda: [
        "Bash",
        "Read",
        "Edit",
    ])

    # Coordinator 工具配置
    coordinator_tools: List[str] = Field(default_factory=lambda: [
        "Agent",
        "SendMessage",
        "TaskStop",
    ])

    # 内部工具（Worker 不可见）
    internal_tools: List[str] = Field(default_factory=lambda: [
        "TeamCreate",
        "TeamDelete",
        "SyntheticOutput",
    ])

    # Scratchpad 配置
    scratchpad_enabled: bool = False
    scratchpad_dir: Optional[str] = None

    # MCP 服务器
    mcp_servers: List[str] = Field(default_factory=list)


def parse_worker_notification(xml_content: str) -> Optional[WorkerNotification]:
    """
    解析 Worker 通知 XML

    格式：
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

        # 提取字段
        task_id = root.find("task-id")
        status = root.find("status")
        summary = root.find("summary")
        result = root.find("result")
        usage_elem = root.find("usage")

        if task_id is None or status is None or summary is None:
            return None

        # 解析 usage
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
    """
    格式化 Worker 通知为 XML

    用于测试和调试
    """
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
