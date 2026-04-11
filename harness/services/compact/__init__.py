"""
Compact Services - 压缩服务模块

提供自动压缩、微压缩等功能。
"""

from .auto_compact import (
    AutoCompactTrackingState,
    TokenWarningState,
    get_effective_context_window_size,
    get_auto_compact_threshold,
    calculate_token_warning_state,
    is_auto_compact_enabled,
    should_auto_compact,
    estimate_tokens,
    auto_compact,
    create_compact_boundary_message,
)

from .micro_compact import (
    MicroCompactResult,
    should_compact_tool,
    estimate_tool_result_tokens,
    should_clear_tool_result,
    clear_tool_result,
    micro_compact,
    create_microcompact_boundary_message,
    try_micro_compact,
    strip_images_from_messages,
    strip_reinjected_attachments,
    COMPACTABLE_TOOLS,
    TIME_BASED_MC_CLEARED_MESSAGE,
)

from .attachments import (
    FileAttachment,
    AttachmentResult,
    create_post_compact_file_attachments,
    format_file_attachment_message,
    create_and_format_file_attachments,
    POST_COMPACT_MAX_FILES_TO_RESTORE,
    POST_COMPACT_TOKEN_BUDGET,
    POST_COMPACT_MAX_TOKENS_PER_FILE,
)

__all__ = [
    # Auto Compact
    "AutoCompactTrackingState",
    "TokenWarningState",
    "get_effective_context_window_size",
    "get_auto_compact_threshold",
    "calculate_token_warning_state",
    "is_auto_compact_enabled",
    "should_auto_compact",
    "estimate_tokens",
    "auto_compact",
    "create_compact_boundary_message",

    # Micro Compact
    "MicroCompactResult",
    "should_compact_tool",
    "estimate_tool_result_tokens",
    "should_clear_tool_result",
    "clear_tool_result",
    "micro_compact",
    "create_microcompact_boundary_message",
    "try_micro_compact",
    "strip_images_from_messages",
    "strip_reinjected_attachments",
    "COMPACTABLE_TOOLS",
    "TIME_BASED_MC_CLEARED_MESSAGE",

    # Attachments
    "FileAttachment",
    "AttachmentResult",
    "create_post_compact_file_attachments",
    "format_file_attachment_message",
    "create_and_format_file_attachments",
    "POST_COMPACT_MAX_FILES_TO_RESTORE",
    "POST_COMPACT_TOKEN_BUDGET",
    "POST_COMPACT_MAX_TOKENS_PER_FILE",
]
