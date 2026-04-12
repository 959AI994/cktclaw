"""
CktMem — file-backed session memory for CktClaw.

Stores markdown memories on disk (no database required for the v2 path).
"""

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

# Legacy SQLite-backed context stack (kept for compatibility)
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
    # File-system memory API
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

    # Legacy database API
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
