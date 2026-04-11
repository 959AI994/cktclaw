"""
Pre-Compact Hooks - 压缩前钩子

在压缩开始前执行的钩子，可以修改压缩行为。
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import asyncio


@dataclass
class PreCompactHookInput:
    """压缩前钩子输入"""
    trigger: str  # "auto" or "manual"
    custom_instructions: Optional[str] = None
    pre_compact_token_count: Optional[int] = None


@dataclass
class PreCompactHookResult:
    """压缩前钩子结果"""
    new_custom_instructions: Optional[str] = None
    user_display_message: Optional[str] = None
    should_cancel: bool = False
    metadata: Optional[Dict[str, Any]] = None


class PreCompactHook:
    """压缩前钩子基类"""

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
        hook_input: PreCompactHookInput,
        abort_signal: Optional[asyncio.Event] = None,
    ) -> PreCompactHookResult:
        """
        执行钩子

        Args:
            hook_input: 钩子输入
            abort_signal: 中止信号

        Returns:
            钩子结果
        """
        raise NotImplementedError


class DefaultPreCompactHook(PreCompactHook):
    """默认的压缩前钩子"""

    def __init__(self):
        super().__init__("default_pre_compact", priority=100)

    async def execute(
        self,
        hook_input: PreCompactHookInput,
        abort_signal: Optional[asyncio.Event] = None,
    ) -> PreCompactHookResult:
        """执行默认钩子"""
        # 默认不做任何修改
        return PreCompactHookResult()


# 全局钩子注册表
_registered_hooks: List[PreCompactHook] = [
    DefaultPreCompactHook(),
]


def register_pre_compact_hook(hook: PreCompactHook):
    """
    注册压缩前钩子

    Args:
        hook: 钩子实例
    """
    _registered_hooks.append(hook)
    # 按优先级排序
    _registered_hooks.sort(key=lambda h: h.priority)


def unregister_pre_compact_hook(name: str):
    """
    注销压缩前钩子

    Args:
        name: 钩子名称
    """
    global _registered_hooks
    _registered_hooks = [h for h in _registered_hooks if h.name != name]


async def execute_pre_compact_hooks(
    hook_input: PreCompactHookInput,
    abort_signal: Optional[asyncio.Event] = None,
) -> PreCompactHookResult:
    """
    执行所有压缩前钩子

    Args:
        hook_input: 钩子输入
        abort_signal: 中止信号

    Returns:
        合并后的钩子结果
    """
    merged_result = PreCompactHookResult()

    for hook in _registered_hooks:
        # 检查是否中止
        if abort_signal and abort_signal.is_set():
            break

        try:
            result = await hook.execute(hook_input, abort_signal)

            # 合并结果
            if result.new_custom_instructions:
                if merged_result.new_custom_instructions:
                    merged_result.new_custom_instructions += "\n\n" + result.new_custom_instructions
                else:
                    merged_result.new_custom_instructions = result.new_custom_instructions

            if result.user_display_message:
                if merged_result.user_display_message:
                    merged_result.user_display_message += "\n" + result.user_display_message
                else:
                    merged_result.user_display_message = result.user_display_message

            if result.should_cancel:
                merged_result.should_cancel = True

            if result.metadata:
                if merged_result.metadata is None:
                    merged_result.metadata = {}
                merged_result.metadata.update(result.metadata)

        except Exception as e:
            # 钩子执行失败不应该阻止压缩
            print(f"Warning: Pre-compact hook '{hook.name}' failed: {e}")
            continue

    return merged_result
