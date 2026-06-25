"""
LLM Types — shared data types for all providers.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MessageRole(str, Enum):
    """Message roles in conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCallDelta:
    """Incremental tool call data from streaming."""
    id: str = ""
    name: str = ""
    arguments_delta: str = ""  # Incremental JSON string
    # When complete
    is_complete: bool = False
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamChunk:
    """A single chunk from streaming LLM output."""
    # Text content (may be partial)
    text_delta: str = ""

    # Tool call (may be partial)
    tool_call_delta: Optional[ToolCallDelta] = None

    # Stream status
    is_done: bool = False

    # Usage stats (only on final chunk)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # Provider-specific metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    """A complete tool call extracted from LLM response."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ToolResultMessage:
    """Result of a tool execution to send back to LLM."""
    tool_call_id: str
    content: str
    is_error: bool = False
