"""
Pydantic models for layered chat messages and compaction metadata.
"""

from enum import Enum
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class MessageRole(str, Enum):
    """Wire-format role strings."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class MessageType(str, Enum):
    """Distinguishes chat traffic from structural compaction rows."""
    CHAT = "chat"
    CORE_CONTEXT = "core_context"
    COMPACT_BOUNDARY = "compact_boundary"
    COMPACT_SUMMARY = "compact_summary"


class ContextLayer(str, Enum):
    """Logical layer for prompt assembly."""
    SYSTEM = "system"
    PROJECT = "project"
    SESSION = "session"
    TURN = "turn"


class Message(BaseModel):
    """Single row mirrored in sqlite ``messages``."""
    role: MessageRole
    content: str
    msg_type: MessageType = MessageType.CHAT
    layer: ContextLayer = ContextLayer.TURN
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    class Config:
        use_enum_values = True


class CompactBoundary(BaseModel):
    """Structured payload embedded in boundary metadata."""
    pre_compact_tokens: int
    compact_type: Literal["auto", "manual", "session_memory", "micro"]
    timestamp: datetime
    anchor_uuid: Optional[str] = None
    preserved_segment_start: Optional[str] = None


class CompactionResult(BaseModel):
    """Output of ``Compactor.auto_compact``."""
    boundary_marker: Message
    summary_messages: List[Message] = Field(default_factory=list)
    messages_to_keep: List[Message] = Field(default_factory=list)
    pre_compact_token_count: int
    post_compact_token_count: int
    compaction_usage: Optional[Dict[str, Any]] = None


class SessionMemoryConfig(BaseModel):
    """Tunable thresholds for session-memory style compaction."""
    min_tokens: int = 10_000
    min_text_messages: int = 5
    max_tokens: int = 40_000


class CompactConfig(BaseModel):
    """Top-level auto-compaction configuration."""
    auto_compact_threshold: int = 150_000
    target_tokens: int = 40_000
    buffer_tokens: int = 13_000
    session_memory: SessionMemoryConfig = Field(default_factory=SessionMemoryConfig)


class AnchorMemory(BaseModel):
    """First-pass circuit snapshot stored on the session row."""
    verilog_code: str
    analysis_report: str
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)
