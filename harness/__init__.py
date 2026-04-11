"""
Harness - CktClaw 架构核心

五大核心模块：
1. Bootstrap (根状态) - 全局状态管理
2. Tasks (任务状态机) - 任务生命周期管理
3. Skills (技能资产化) - 技能注册与执行
4. Coordinator (调度隔离) - 多智能体调度
5. Query (中枢循环) - Tool-Result 配对与自愈

设计原则：
- 单例模式（全局管理器）
- 线程安全（asyncio.Lock）
- 状态最小化（DO NOT ADD MORE STATE）
- 不可变状态（每次迭代创建新状态）
- 错误自愈（自动修复常见错误）
"""

# Bootstrap
from .bootstrap import (
    BootstrapState,
    StateManager,
    get_state_manager,
)

# Tasks
from .tasks import (
    TaskType,
    TaskStatus,
    TaskStateBase,
    TaskManager,
    get_task_manager,
)

# Skills
from .skills import (
    SkillType,
    SkillDefinition,
    LoadedFrom,
    SkillRegistry,
    get_skill_registry,
    register_skill,
    get_skill,
    list_skills,
)

# Coordinator
from .coordinator import (
    CoordinatorMode,
    WorkerNotification,
    NotificationStatus,
    CoordinatorManager,
    get_coordinator_manager,
    is_coordinator_mode,
    get_worker_tools_context,
    get_coordinator_system_prompt,
)

# Query
from .query import (
    QueryState,
    QueryConfig,
    QueryResult,
    ContinueReason,
    TerminalReason,
    QueryLoop,
    create_query_loop,
    run_query,
)

__version__ = "1.0.0"

__all__ = [
    # Bootstrap
    "BootstrapState",
    "StateManager",
    "get_state_manager",

    # Tasks
    "TaskType",
    "TaskStatus",
    "TaskStateBase",
    "TaskManager",
    "get_task_manager",

    # Skills
    "SkillType",
    "SkillDefinition",
    "LoadedFrom",
    "SkillRegistry",
    "get_skill_registry",
    "register_skill",
    "get_skill",
    "list_skills",

    # Coordinator
    "CoordinatorMode",
    "WorkerNotification",
    "NotificationStatus",
    "CoordinatorManager",
    "get_coordinator_manager",
    "is_coordinator_mode",
    "get_worker_tools_context",
    "get_coordinator_system_prompt",

    # Query
    "QueryState",
    "QueryConfig",
    "QueryResult",
    "ContinueReason",
    "TerminalReason",
    "QueryLoop",
    "create_query_loop",
    "run_query",
]
