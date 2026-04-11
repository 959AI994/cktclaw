"""
CktMem - 基于文件系统的记忆管理系统

完全重构，参考 Claude Code 的 memdir 实现
使用磁盘上的 markdown 文件而不是数据库
"""

# 新的文件系统记忆模块
from .paths import (
    get_auto_mem_path,
    get_project_root,
    is_auto_memory_enabled,
    is_auto_mem_path,
    ENTRYPOINT_NAME,
    MAX_ENTRYPOINT_LINES,
    MAX_ENTRYPOINT_BYTES,
)

from .memory_types import (
    MEMORY_TYPES,
    build_memory_guidelines,
)

from .memdir import (
    load_memory_prompt,
    ensure_memory_dir_exists,
    truncate_entrypoint_content,
)

from .memory_scan import (
    scan_memory_files,
    format_memory_manifest,
    parse_frontmatter,
)

from .find_relevant_memories import (
    find_relevant_memories,
    load_memory_contents,
)

# 保留旧模块以兼容现有代码
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

__version__ = "2.0.0"

__all__ = [
    # 新的文件系统记忆 API
    "get_auto_mem_path",
    "get_project_root",
    "is_auto_memory_enabled",
    "is_auto_mem_path",
    "ENTRYPOINT_NAME",
    "MEMORY_TYPES",
    "build_memory_guidelines",
    "load_memory_prompt",
    "ensure_memory_dir_exists",
    "truncate_entrypoint_content",
    "scan_memory_files",
    "format_memory_manifest",
    "parse_frontmatter",
    "find_relevant_memories",
    "load_memory_contents",

    # 旧的数据库记忆 API（兼容性）
    "ContextManager",
    "Storage",
    "Compactor",
    "TokenCounter",
    "Message",
    "MessageRole",
    "MessageType",
    "ContextLayer",
    "CompactConfig",
    "SessionMemoryConfig",
    "CompactionResult",
    "CompactBoundary",
    "AnchorMemory",
    "format_timestamp",
    "truncate_text",
    "estimate_text_tokens",
    "calculate_compression_ratio",
]

