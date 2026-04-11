"""
Hooks System - 钩子系统

提供压缩前后和会话启动时的钩子机制。
"""

from .pre_compact import (
    PreCompactHookInput,
    PreCompactHookResult,
    execute_pre_compact_hooks,
)

from .post_compact import (
    PostCompactHookInput,
    PostCompactHookResult,
    execute_post_compact_hooks,
)

from .session_start import (
    SessionStartHookInput,
    SessionStartHookResult,
    execute_session_start_hooks,
)

__all__ = [
    # Pre Compact
    "PreCompactHookInput",
    "PreCompactHookResult",
    "execute_pre_compact_hooks",

    # Post Compact
    "PostCompactHookInput",
    "PostCompactHookResult",
    "execute_post_compact_hooks",

    # Session Start
    "SessionStartHookInput",
    "SessionStartHookResult",
    "execute_session_start_hooks",
]
