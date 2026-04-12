"""
Coordinator manager — multi-worker routing and prompts.

Responsibilities:
1. Track coordinator vs normal mode
2. Build worker tool contexts
3. Produce coordinator-specific system prompts
4. Fan-out worker notifications

Design:
- Single shared instance for the process
- asyncio.Lock around mutable coordinator tables
- Strict separation between coordinator and standalone REPL paths
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
    Singleton coordinator facade.

    Tracks mode, worker tool lists, and coordinator-only prompts.
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
        """Return a copy of the live CoordinatorConfig."""
        return self._config.copy()

    async def set_mode(self, mode: CoordinatorMode) -> None:
        """Force coordinator vs normal mode."""
        async with self._manager_lock:
            self._config.mode = mode

    async def get_mode(self) -> CoordinatorMode:
        """Current CoordinatorMode enum value."""
        async with self._manager_lock:
            return self._config.mode

    async def is_coordinator_mode(self) -> bool:
        """True when multi-worker coordinator routing is active."""
        mode = await self.get_mode()
        return mode == CoordinatorMode.COORDINATOR

    async def match_session_mode(
        self,
        session_mode: Optional[str],
    ) -> Optional[str]:
        """
        Align in-memory mode with a persisted session flag.

        Args:
            session_mode: Stored value "coordinator" or "normal".

        Returns:
            Human-readable warning when the mode flips, else None.
        """
        if not session_mode:
            return None

        async with self._manager_lock:
            current_is_coordinator = self._config.mode == CoordinatorMode.COORDINATOR
            session_is_coordinator = session_mode == "coordinator"

            if current_is_coordinator == session_is_coordinator:
                return None

            if session_is_coordinator:
                self._config.mode = CoordinatorMode.COORDINATOR
                return "Entered coordinator mode to match resumed session."
            else:
                self._config.mode = CoordinatorMode.NORMAL
                return "Exited coordinator mode to match resumed session."

    async def get_worker_tools_context(self) -> Dict[str, str]:
        """
        Build the workerToolsContext payload for downstream agents.

        Returns:
            Dict with key ``workerToolsContext`` describing tools + MCP + scratchpad.
        """
        async with self._manager_lock:
            if self._config.mode != CoordinatorMode.COORDINATOR:
                return {}

            worker_tools = sorted([
                tool for tool in self._config.worker_tools
                if tool not in self._config.internal_tools
            ])

            content = f"Workers spawned via the Agent tool have access to these tools: {', '.join(worker_tools)}"

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
        Long-form coordinator system prompt (empty when not in coordinator mode).
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
        Parse embedded <task-notification> XML from assistant/user traffic.

        Args:
            content: Raw message body that may include XML.

        Returns:
            Parsed WorkerNotification or None when parsing fails.
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
        Patch coordinator fields in place.

        Args:
            mode: Optional CoordinatorMode override.
            worker_tools: Replace worker-visible tool allowlist.
            mcp_servers: Connected MCP server display names.
            scratchpad_dir: Shared scratch directory for workers.
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
        """Restore defaults (tests only)."""
        self._config = CoordinatorConfig()


_coordinator_manager: Optional[CoordinatorManager] = None


def get_coordinator_manager() -> CoordinatorManager:
    """Lazy singleton accessor."""
    global _coordinator_manager
    if _coordinator_manager is None:
        _coordinator_manager = CoordinatorManager()
    return _coordinator_manager


async def is_coordinator_mode() -> bool:
    """Module-level coordinator mode probe."""
    return await get_coordinator_manager().is_coordinator_mode()


async def get_worker_tools_context() -> Dict[str, str]:
    """Module-level workerToolsContext helper."""
    return await get_coordinator_manager().get_worker_tools_context()


async def get_coordinator_system_prompt() -> str:
    """Module-level coordinator prompt helper."""
    return await get_coordinator_manager().get_coordinator_system_prompt()
