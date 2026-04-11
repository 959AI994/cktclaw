"""
CktMem - 四层上下文记忆管理系统

提供：
- 四层上下文模型（System/Project/Session/Turn）
- 自动上下文压缩
- 边界隔离标记
- Token 估算与管理
"""

from .models import (
    Message,
    MessageRole,
    MessageType,
    ContextLayer,
    CompactConfig,
    SessionMemoryConfig,
    CompactionResult,
    CompactBoundary,
    AnchorMemory,
)

from .manager import ContextManager
from .storage import Storage
from .compactor import Compactor
from .token_counter import TokenCounter
from .utils import (
    format_timestamp,
    truncate_text,
    estimate_text_tokens,
    calculate_compression_ratio,
)

__version__ = "0.1.0"

__all__ = [
    # Core classes
    "ContextManager",
    "Storage",
    "Compactor",
    "TokenCounter",

    # Models
    "Message",
    "MessageRole",
    "MessageType",
    "ContextLayer",
    "CompactConfig",
    "SessionMemoryConfig",
    "CompactionResult",
    "CompactBoundary",
    "AnchorMemory",

    # Utils
    "format_timestamp",
    "truncate_text",
    "estimate_text_tokens",
    "calculate_compression_ratio",
]
