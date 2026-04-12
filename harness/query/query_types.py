"""
Query loop types — enums, config, and result models.

Defines:
1. Query / transition enums
2. Continue vs terminal reasons
3. QueryConfig
4. QueryResult and tool blocks

Design:
- Explicit state machine (continue vs terminal)
- Immutable-style snapshots per iteration (Pydantic models)
- Recovery hooks (e.g. max_output_tokens paths)
- Token / budget fields on config and results
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TransitionType(str, Enum):
    """Edge type in the high-level transition graph."""
    CONTINUE = "continue"  # loop again
    TERMINAL = "terminal"  # stop


class ContinueReason(str, Enum):
    """Why the loop continues after a step."""
    TOOL_USE = "tool_use"
    MAX_OUTPUT_TOKENS = "max_output_tokens"
    REACTIVE_COMPACT = "reactive_compact"
    AUTO_COMPACT = "auto_compact"
    BUDGET_CONTINUATION = "budget_continuation"


class TerminalReason(str, Enum):
    """Why the loop stopped."""
    END_TURN = "end_turn"
    MAX_TURNS = "max_turns"
    BUDGET_EXCEEDED = "budget_exceeded"
    ERROR = "error"
    USER_INTERRUPT = "user_interrupt"


class AutoCompactTracking(BaseModel):
    """Tracks repeated auto-compact attempts (circuit breaker)."""
    consecutive_failures: int = 0
    last_attempt_tokens: int = 0
    last_attempt_time: Optional[datetime] = None


class QueryState(BaseModel):
    """
    Mutable loop snapshot passed between iterations.

    Holds messages, compaction flags, and counters.
    """
    messages: List[Dict[str, Any]] = Field(default_factory=list)

    tool_use_context: Dict[str, Any] = Field(default_factory=dict)

    auto_compact_tracking: Optional[AutoCompactTracking] = None

    max_output_tokens_recovery_count: int = 0

    has_attempted_reactive_compact: bool = False

    max_output_tokens_override: Optional[int] = None

    stop_hook_active: Optional[bool] = None

    turn_count: int = 1

    transition: Optional[ContinueReason] = None

    class Config:
        arbitrary_types_allowed = True


class QueryConfig(BaseModel):
    """Tunables for one query / session."""
    system_prompt: str

    user_context: Dict[str, str] = Field(default_factory=dict)

    system_context: Dict[str, str] = Field(default_factory=dict)

    max_turns: Optional[int] = None

    max_budget_usd: Optional[float] = None

    token_budget: Optional[int] = None

    auto_compact_threshold: int = 150_000

    target_tokens: int = 40_000

    auto_compact_enabled: bool = True

    reactive_compact_enabled: bool = False

    skip_cache_write: bool = False

    query_source: str = "unknown"


class QueryStateEnum(str, Enum):
    """UI / orchestration state for the current step."""
    IDLE = "idle"
    LLM_CALLING = "llm_calling"
    TOOL_EXECUTING = "tool_executing"
    COMPACTING = "compacting"
    SELF_HEALING = "self_healing"
    CONTINUING = "continuing"
    TERMINAL = "terminal"


class QueryResult(BaseModel):
    """One yielded step from the query loop."""
    state: QueryStateEnum = QueryStateEnum.IDLE

    terminal_reason: Optional[TerminalReason] = None

    final_response: Optional[str] = None

    current_tool_name: Optional[str] = None

    error_message: Optional[str] = None

    messages: List[Dict[str, Any]] = Field(default_factory=list)

    total_turns: int = 0

    total_tokens: int = 0

    total_cost: float = 0.0

    tool_calls: int = 0

    compactions: int = 0

    created_at: datetime = Field(default_factory=datetime.now)


class ToolUseBlock(BaseModel):
    """Anthropic-style tool_use block."""
    id: str
    type: str = "tool_use"
    name: str
    input: Dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    """Anthropic-style tool_result block."""
    type: str = "tool_result"
    tool_use_id: str
    content: str
    is_error: bool = False


def validate_tool_result_pairing(messages: List[Dict[str, Any]]) -> List[str]:
    """
    Return tool_use ids that have no matching tool_result.

    Args:
        messages: Transcript messages (assistant/user with block lists)

    Returns:
        List of missing tool_use_id strings
    """
    tool_use_ids = set()
    tool_result_ids = set()

    for msg in messages:
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_use_ids.add(block.get("id"))

        if msg.get("role") == "user":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_result_ids.add(block.get("tool_use_id"))

    missing = tool_use_ids - tool_result_ids
    return list(missing)


def create_missing_tool_results(
    missing_ids: List[str],
    error_message: str = "Tool execution was interrupted",
) -> List[Dict[str, Any]]:
    """
    Build synthetic user messages with tool_result blocks for missing ids.

    Args:
        missing_ids: tool_use ids without results
        error_message: Text stored in the synthetic tool_result

    Returns:
        List of user-shaped messages wrapping tool_result blocks
    """
    results = []
    for tool_use_id in missing_ids:
        results.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": error_message,
                    "is_error": True,
                }
            ],
        })
    return results
