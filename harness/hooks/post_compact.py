"""
Post-Compact Hooks - 压缩后钩子

在压缩完成后执行的钩子，可以处理压缩结果。
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import asyncio


@dataclass
class PostCompactHookInput:
    """压缩后钩子输入"""
    trigger: str  # "auto" or "manual"
    compact_summary: str
    pre_compact_token_count: Optional[int] = None
    post_compact_token_count: Optional[int] = None
    tokens_saved: Optional[int] = None


@dataclass
class PostCompactHookResult:
    """压缩后钩子结果"""
    user_display_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PostCompactHook:
    """压缩后钩子基类"""

    def __init__(self, name: str, priority: int = 100):
        """
        初始化钩子

        Args:
            name: 钩子名称
            priority: 优先级（数字越小越先执行）
        """
        self.name = name
        self.priority = priority

    async def execute(
        self,
        hook_input: PostCompactHookInput,
        abort_signal: Optional[asyncio.Event] = None,
    ) -> PostCompactHookResult:
        """
        执行钩子

        Args:
            hook_input: 钩子输入
            abort_signal: 中止信号

        Returns:
            钩子结果
        """
        raise NotImplementedError


class DefaultPostCompactHook(PostCompactHook):
    """默认的压缩后钩子"""

    def __init__(self):
        super().__init__("default_post_compact", priority=100)

    async def execute(
        self,
        hook_input: PostCompactHookInput,
        abort_signal: Optional[asyncio.Event] = None,
    ) -> PostCompactHookResult:
        """执行默认钩子"""
        # 生成默认的用户显示消息
        if hook_input.tokens_saved:
            message = f"💾 Compacted conversation, saved ~{hook_input.tokens_saved:,} tokens"
        else:
            message = "💾 Compacted conversation"

        return PostCompactHookResult(
            user_display_message=message,
        )


class LoggingPostCompactHook(PostCompactHook):
    """日志记录钩子"""

    def __init__(self):
        super().__init__("logging_post_compact", priority=50)

    async def execute(
        self,
        hook_input: PostCompactHookInput,
        abort_signal: Optional[asyncio.Event] = None,
    ) -> PostCompactHookResult:
        """记录压缩信息"""
        print(f"[Compact] Trigger: {hook_input.trigger}")
        print(f"[Compact] Pre-compact tokens: {hook_input.pre_compact_token_count}")
        print(f"[Compact] Post-compact tokens: {hook_input.post_compact_token_count}")
        print(f"[Compact] Tokens saved: {hook_input.tokens_saved}")

        return PostCompactHookResult()


# 全局钩子注册表
_registered_hooks: List[PostCompactHook] = [
    LoggingPostCompactHook(),
    DefaultPostCompactHook(),
]


def register_post_compact_hook(hook: PostCompactHook):
    """
    注册压缩后钩子

    Args:
        hook: 钩子实例
    """
    _registered_hooks.append(hook)
    # 按优先级排序
    _registered_hooks.sort(key=lambda h: h.priority)


def unregister_post_compact_hook(name: str):
    """
    注销压缩后钩子

    Args:
        name: 钩子名称
    """
    global _registered_hooks
    _registered_hooks = [h for h in _registered_hooks if h.name != name]


async def execute_post_compact_hooks(
    hook_input: PostCompactHookInput,
    abort_signal: Optional[asyncio.Event] = None,
) -> PostCompactHookResult:
    """
    执行所有压缩后钩子

    Args:
        hook_input: 钩子输入
        abort_signal: 中止信号

    Returns:
        合并后的钩子结果
    """
    merged_result = PostCompactHookResult()

    for hook in _registered_hooks:
        # 检查是否中止
        if abort_signal and abort_signal.is_set():
            break

        try:
            result = await hook.execute(hook_input, abort_signal)

            # 合并结果
            if result.user_display_message:
                if merged_result.user_display_message:
                    merged_result.user_display_message += "\n" + result.user_display_message
                else:
                    merged_result.user_display_message = result.user_display_message

            if result.metadata:
                if merged_result.metadata is None:
                    merged_result.metadata = {}
                merged_result.metadata.update(result.metadata)

        except Exception as e:
            # 钩子执行失败不应该阻止后续处理
            print(f"Warning: Post-compact hook '{hook.name}' failed: {e}")
            continue

    return merged_result
