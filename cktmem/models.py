"""
CktMem 数据模型定义

定义四层上下文模型的核心数据结构
"""

from enum import Enum
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class MessageType(str, Enum):
    """消息类型"""
    CHAT = "chat"                    # 普通对话
    CORE_CONTEXT = "core_context"    # 核心上下文（电路分析结果）
    COMPACT_BOUNDARY = "compact_boundary"  # 压缩边界
    COMPACT_SUMMARY = "compact_summary"    # 压缩摘要


class ContextLayer(str, Enum):
    """上下文层级"""
    SYSTEM = "system"
    PROJECT = "project"
    SESSION = "session"
    TURN = "turn"


class Message(BaseModel):
    """统一消息结构"""
    role: MessageRole
    content: str
    msg_type: MessageType = MessageType.CHAT
    layer: ContextLayer = ContextLayer.TURN
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # 可选字段
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    class Config:
        use_enum_values = True


class CompactBoundary(BaseModel):
    """压缩边界标记"""
    pre_compact_tokens: int
    compact_type: Literal["auto", "manual", "session_memory", "micro"]
    timestamp: datetime
    anchor_uuid: Optional[str] = None
    preserved_segment_start: Optional[str] = None


class CompactionResult(BaseModel):
    """压缩结果"""
    boundary_marker: Message
    summary_messages: List[Message] = Field(default_factory=list)
    messages_to_keep: List[Message] = Field(default_factory=list)
    pre_compact_token_count: int
    post_compact_token_count: int
    compaction_usage: Optional[Dict[str, Any]] = None


class SessionMemoryConfig(BaseModel):
    """Session Memory 压缩配置"""
    min_tokens: int = 10_000
    min_text_messages: int = 5
    max_tokens: int = 40_000


class CompactConfig(BaseModel):
    """压缩配置"""
    auto_compact_threshold: int = 150_000
    target_tokens: int = 40_000
    buffer_tokens: int = 13_000
    session_memory: SessionMemoryConfig = Field(default_factory=SessionMemoryConfig)


class AnchorMemory(BaseModel):
    """Anchor Memory（首份核心上下文）"""
    verilog_code: str
    analysis_report: str
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)
