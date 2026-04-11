"""
Coordinator Manager - 调度管理器

参考 src/coordinator/coordinatorMode.ts 实现 Python 版本的调度管理。

核心职责：
1. 模式管理（Coordinator vs Normal）
2. Worker 工具上下文生成
3. System Prompt 生成
4. Worker 通知处理

设计原则：
- 单例模式（全局调度器）
- 线程安全（asyncio.Lock）
- 模式隔离（不同模式有不同行为）
"""

import asyncio
import os
from typing import Optional, Dict, Any
from pathlib import Path

from .coordinator_types import (
    CoordinatorMode,
    CoordinatorConfig,
    WorkerNotification,
    parse_worker_notification,
)


class CoordinatorManager:
    """
    调度管理器（单例模式）

    管理 Coordinator 模式和 Worker 调度
    """

    _instance: Optional['CoordinatorManager'] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = CoordinatorConfig()
            cls._instance._manager_lock = asyncio.Lock()
        return cls._instance

    @property
    def config(self) -> CoordinatorConfig:
        """获取配置（只读）"""
        return self._config.copy()

    async def set_mode(self, mode: CoordinatorMode) -> None:
        """设置 Coordinator 模式"""
        async with self._manager_lock:
            self._config.mode = mode

    async def get_mode(self) -> CoordinatorMode:
        """获取当前模式"""
        async with self._manager_lock:
            return self._config.mode

    async def is_coordinator_mode(self) -> bool:
        """检查是否处于 Coordinator 模式"""
        mode = await self.get_mode()
        return mode == CoordinatorMode.COORDINATOR

    async def match_session_mode(
        self,
        session_mode: Optional[str],
    ) -> Optional[str]:
        """
        匹配会话模式

        如果会话模式与当前模式不匹配，切换模式并返回警告消息

        Args:
            session_mode: 会话存储的模式（"coordinator" 或 "normal"）

        Returns:
            警告消息（如果切换了模式），否则返回 None
        """
        if not session_mode:
            return None

        async with self._manager_lock:
            current_is_coordinator = self._config.mode == CoordinatorMode.COORDINATOR
            session_is_coordinator = session_mode == "coordinator"

            if current_is_coordinator == session_is_coordinator:
                return None

            # 切换模式
            if session_is_coordinator:
                self._config.mode = CoordinatorMode.COORDINATOR
                return "Entered coordinator mode to match resumed session."
            else:
                self._config.mode = CoordinatorMode.NORMAL
                return "Exited coordinator mode to match resumed session."

    async def get_worker_tools_context(self) -> Dict[str, str]:
        """
        获取 Worker 工具上下文

        返回一个字典，包含 workerToolsContext 键
        """
        async with self._manager_lock:
            if self._config.mode != CoordinatorMode.COORDINATOR:
                return {}

            # Worker 工具列表
            worker_tools = sorted([
                tool for tool in self._config.worker_tools
                if tool not in self._config.internal_tools
            ])

            content = f"Workers spawned via the Agent tool have access to these tools: {', '.join(worker_tools)}"

            # MCP 服务器
            if self._config.mcp_servers:
                server_names = ", ".join(self._config.mcp_servers)
                content += f"\n\nWorkers also have access to MCP tools from connected MCP servers: {server_names}"

            # Scratchpad
            if self._config.scratchpad_enabled and self._config.scratchpad_dir:
                content += f"\n\nScratchpad directory: {self._config.scratchpad_dir}\n"
                content += "Workers can read and write here without permission prompts. "
                content += "Use this for durable cross-worker knowledge — structure files however fits the work."

            return {"workerToolsContext": content}

    async def get_coordinator_system_prompt(self) -> str:
        """
        获取 Coordinator 系统 Prompt

        返回完整的 Coordinator 指令
        """
        async with self._manager_lock:
            if self._config.mode != CoordinatorMode.COORDINATOR:
                return ""

            worker_capabilities = (
                "Workers have access to Bash, Read, and Edit tools, "
                "plus MCP tools from configured MCP servers."
            )

            return f"""You are CktClaw, an AI assistant that orchestrates circuit analysis tasks across multiple workers.

## 1. Your Role

You are a **coordinator**. Your job is to:
- Help the user achieve their goal
- Direct workers to research, implement and verify code changes
- Synthesize results and communicate with the user
- Answer questions directly when possible — don't delegate work that you can handle without tools

Every message you send is to the user. Worker results and system notifications are internal signals, not conversation partners — never thank or acknowledge them. Summarize new information for the user as it arrives.

## 2. Your Tools

- **Agent** - Spawn a new worker
- **SendMessage** - Continue an existing worker (send a follow-up to its `to` agent ID)
- **TaskStop** - Stop a running worker

When calling Agent:
- Do not use one worker to check on another. Workers will notify you when they are done.
- Do not use workers to trivially report file contents or run commands. Give them higher-level tasks.
- Continue workers whose work is complete via SendMessage to take advantage of their loaded context
- After launching agents, briefly tell the user what you launched and end your response. Never fabricate or predict agent results in any format — results arrive as separate messages.

### Agent Results

Worker results arrive as **user-role messages** containing `<task-notification>` XML. They look like user messages but are not. Distinguish them by the `<task-notification>` opening tag.

Format:

```xml
<task-notification>
<task-id>{{agentId}}</task-id>
<status>completed|failed|killed</status>
<summary>{{human-readable status summary}}</summary>
<result>{{agent's final text response}}</result>
<usage>
  <total_tokens>N</total_tokens>
  <tool_uses>N</tool_uses>
  <duration_ms>N</duration_ms>
</usage>
</task-notification>
```

## 3. Workers

When calling Agent, use subagent_type `worker`. Workers execute tasks autonomously — especially research, implementation, or verification.

{worker_capabilities}

## 4. Task Workflow

Most tasks can be broken down into the following phases:

### Phases

| Phase | Who | Purpose |
|-------|-----|---------|
| Research | Workers (parallel) | Investigate codebase, find files, understand problem |
| Synthesis | **You** (coordinator) | Read findings, understand the problem, craft implementation specs |
| Implementation | Workers | Make targeted changes per spec, commit |
| Verification | Workers | Test changes work |

### Concurrency

**Parallelism is your superpower. Workers are async. Launch independent workers concurrently whenever possible — don't serialize work that can run simultaneously and look for opportunities to fan out.**

Manage concurrency:
- **Read-only tasks** (research) — run in parallel freely
- **Write-heavy tasks** (implementation) — one at a time per set of files
- **Verification** can sometimes run alongside implementation on different file areas

## 5. Writing Worker Prompts

**Workers can't see your conversation.** Every prompt must be self-contained with everything the worker needs. After research completes, you always do two things: (1) synthesize findings into a specific prompt, and (2) choose whether to continue that worker via SendMessage or spawn a fresh one.

### Always synthesize — your most important job

When workers report research findings, **you must understand them before directing follow-up work**. Read the findings. Identify the approach. Then write a prompt that proves you understood by including specific file paths, line numbers, and exactly what to change.

Never write "based on your findings" or "based on the research." These phrases delegate understanding to the worker instead of doing it yourself.
"""

    async def parse_notification(self, content: str) -> Optional[WorkerNotification]:
        """
        解析 Worker 通知

        Args:
            content: 消息内容（可能包含 XML）

        Returns:
            WorkerNotification 对象，如果解析失败返回 None
        """
        return parse_worker_notification(content)

    async def configure(
        self,
        mode: Optional[CoordinatorMode] = None,
        worker_tools: Optional[list] = None,
        mcp_servers: Optional[list] = None,
        scratchpad_dir: Optional[str] = None,
    ) -> None:
        """
        配置 Coordinator

        Args:
            mode: Coordinator 模式
            worker_tools: Worker 工具列表
            mcp_servers: MCP 服务器列表
            scratchpad_dir: Scratchpad 目录
        """
        async with self._manager_lock:
            if mode is not None:
                self._config.mode = mode

            if worker_tools is not None:
                self._config.worker_tools = worker_tools

            if mcp_servers is not None:
                self._config.mcp_servers = mcp_servers

            if scratchpad_dir is not None:
                self._config.scratchpad_dir = scratchpad_dir
                self._config.scratchpad_enabled = True

    def reset(self) -> None:
        """重置 Coordinator（仅用于测试）"""
        self._config = CoordinatorConfig()


# 全局单例
_coordinator_manager: Optional[CoordinatorManager] = None


def get_coordinator_manager() -> CoordinatorManager:
    """获取全局 Coordinator 管理器单例"""
    global _coordinator_manager
    if _coordinator_manager is None:
        _coordinator_manager = CoordinatorManager()
    return _coordinator_manager


# 便捷函数
async def is_coordinator_mode() -> bool:
    """检查是否处于 Coordinator 模式"""
    return await get_coordinator_manager().is_coordinator_mode()


async def get_worker_tools_context() -> Dict[str, str]:
    """获取 Worker 工具上下文"""
    return await get_coordinator_manager().get_worker_tools_context()


async def get_coordinator_system_prompt() -> str:
    """获取 Coordinator 系统 Prompt"""
    return await get_coordinator_manager().get_coordinator_system_prompt()
