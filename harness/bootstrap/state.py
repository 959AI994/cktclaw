"""
Bootstrap state — minimal process-wide session and counters.

Responsibilities:
1. Hold shared fields (cwd, project root, session id, usage counters)
2. Expose small atomic-style mutators (no ad-hoc global writes)
3. Serialize access where needed (async locks on hot paths)
4. Keep the surface area tiny — extend via services, not new globals

Rules:
- DO NOT ADD MORE STATE HERE - BE JUDICIOUS WITH GLOBAL STATE
- Prefer dedicated modules for new concerns
- Validate with Pydantic models at the edges
- asyncio.Lock serializes concurrent mutators
"""

import asyncio
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any
from uuid import uuid4
from pydantic import BaseModel, Field


class ModelUsage(BaseModel):
    """Per-model token usage aggregates."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


class BootstrapState(BaseModel):
    """Minimal mutable process snapshot (keep this struct small)."""

    # Working directory
    original_cwd: str = Field(default_factory=lambda: os.getcwd())
    project_root: str = Field(default_factory=lambda: os.getcwd())
    cwd: str = Field(default_factory=lambda: os.getcwd())

    # Session
    session_id: str = Field(default_factory=lambda: uuid4().hex[:16])
    start_time: float = Field(default_factory=time.time)
    last_interaction_time: float = Field(default_factory=time.time)

    # Cost / latency totals
    total_cost_usd: float = 0.0
    total_api_duration: float = 0.0
    total_api_duration_without_retries: float = 0.0
    total_tool_duration: float = 0.0

    # Per-turn counters (reset each turn)
    turn_hook_duration_ms: float = 0.0
    turn_tool_duration_ms: float = 0.0
    turn_classifier_duration_ms: float = 0.0
    turn_tool_count: int = 0
    turn_hook_count: int = 0
    turn_classifier_count: int = 0

    # Code churn
    total_lines_added: int = 0
    total_lines_removed: int = 0

    # Model usage
    model_usage: Dict[str, ModelUsage] = Field(default_factory=dict)
    has_unknown_model_cost: bool = False

    # Misc flags
    is_interactive: bool = True
    strict_tool_result_pairing: bool = False
    client_type: str = "cli"

    class Config:
        arbitrary_types_allowed = True


class StateManager:
    """
    Process-wide state holder (singleton).

    All mutators run under an asyncio lock for consistency.
    """

    _instance: Optional['StateManager'] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._state = BootstrapState()
            cls._instance._state_lock = asyncio.Lock()
        return cls._instance

    @property
    def state(self) -> BootstrapState:
        """Return the current snapshot (callers must not mutate fields in place)."""
        return self._state

    async def get_session_id(self) -> str:
        """Return the active session id."""
        async with self._state_lock:
            return self._state.session_id

    async def get_cwd(self) -> str:
        """Return the resolved working directory."""
        async with self._state_lock:
            return self._state.cwd

    async def set_cwd(self, cwd: str) -> None:
        """Update working directory to an absolute path."""
        async with self._state_lock:
            self._state.cwd = str(Path(cwd).resolve())

    async def get_project_root(self) -> str:
        """Return the configured project root."""
        async with self._state_lock:
            return self._state.project_root

    async def update_last_interaction_time(self) -> None:
        """Bump last-interaction timestamp (wall clock)."""
        async with self._state_lock:
            self._state.last_interaction_time = time.time()

    async def add_model_usage(
        self,
        model_name: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ) -> None:
        """Accumulate token usage for a named model."""
        async with self._state_lock:
            if model_name not in self._state.model_usage:
                self._state.model_usage[model_name] = ModelUsage()

            usage = self._state.model_usage[model_name]
            usage.input_tokens += input_tokens
            usage.output_tokens += output_tokens
            usage.cache_creation_input_tokens += cache_creation_input_tokens
            usage.cache_read_input_tokens += cache_read_input_tokens

    async def add_cost(self, cost_usd: float) -> None:
        """Add billed USD to the running total."""
        async with self._state_lock:
            self._state.total_cost_usd += cost_usd

    async def add_api_duration(self, duration: float, with_retries: bool = True) -> None:
        """Record API wall time (optionally excluding retry overhead)."""
        async with self._state_lock:
            self._state.total_api_duration += duration
            if not with_retries:
                self._state.total_api_duration_without_retries += duration

    async def add_tool_duration(self, duration: float) -> None:
        """Record aggregate tool execution time."""
        async with self._state_lock:
            self._state.total_tool_duration += duration

    async def increment_turn_tool_count(self) -> None:
        """Increment per-turn tool-use counter."""
        async with self._state_lock:
            self._state.turn_tool_count += 1

    async def increment_turn_hook_count(self) -> None:
        """Increment per-turn hook counter."""
        async with self._state_lock:
            self._state.turn_hook_count += 1

    async def reset_turn_counters(self) -> None:
        """Clear per-turn latency and counters (new assistant turn)."""
        async with self._state_lock:
            self._state.turn_hook_duration_ms = 0.0
            self._state.turn_tool_duration_ms = 0.0
            self._state.turn_classifier_duration_ms = 0.0
            self._state.turn_tool_count = 0
            self._state.turn_hook_count = 0
            self._state.turn_classifier_count = 0

    async def add_lines_changed(self, added: int, removed: int) -> None:
        """Track cumulative line add/remove totals."""
        async with self._state_lock:
            self._state.total_lines_added += added
            self._state.total_lines_removed += removed

    async def get_stats(self) -> Dict[str, Any]:
        """Return a JSON-friendly stats dict for dashboards / logs."""
        async with self._state_lock:
            return {
                "session_id": self._state.session_id,
                "uptime": time.time() - self._state.start_time,
                "total_cost_usd": self._state.total_cost_usd,
                "total_api_duration": self._state.total_api_duration,
                "total_tool_duration": self._state.total_tool_duration,
                "total_lines_added": self._state.total_lines_added,
                "total_lines_removed": self._state.total_lines_removed,
                "model_usage": {
                    name: usage.dict()
                    for name, usage in self._state.model_usage.items()
                },
            }

    def reset(self) -> None:
        """Replace state with a fresh BootstrapState (tests only)."""
        self._state = BootstrapState()


# Module-level singleton handle
_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """Lazily construct and return the shared StateManager."""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager


# Thin wrappers (async entrypoints for callers without direct manager access)
async def get_session_id() -> str:
    """Session id for the active process."""
    return await get_state_manager().get_session_id()


async def get_cwd() -> str:
    """Current working directory."""
    return await get_state_manager().get_cwd()


async def set_cwd(cwd: str) -> None:
    """Update cwd for subprocesses / tools."""
    await get_state_manager().set_cwd(cwd)


async def get_project_root() -> str:
    """Project root path."""
    return await get_state_manager().get_project_root()
