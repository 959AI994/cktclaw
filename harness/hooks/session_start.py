"""
Session Start Hooks - 会话启动钩子

在会话启动时执行的钩子，可以初始化会话状态。
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import asyncio


@dataclass
class SessionStartHookInput:
    """会话启动钩子输入"""
    trigger: str  # "new_session", "compact", "resume"
    session_id: Optional[str] = None
    model: Optional[str] = None


@dataclass
class SessionStartHookResult:
    """会话启动钩子结果"""
    messages: List[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]] = None


class SessionStartHook:
    """会话启动钩子基类"""

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
        hook_input: SessionStartHookInput,
        abort_signal: Optional[asyncio.Event] = None,
    ) -> SessionStartHookResult:
        """
        执行钩子

        Args:
            hook_input: 钩子输入
            abort_signal: 中止信号

        Returns:
            钩子结果
        """
        raise NotImplementedError


class WelcomeMessageHook(SessionStartHook):
    """欢迎消息钩子"""

    def __init__(self):
        super().__init__("welcome_message", priority=50)

    async def execute(
        self,
        hook_input: SessionStartHookInput,
        abort_signal: Optional[asyncio.Event] = None,
    ) -> SessionStartHookResult:
        """生成欢迎消息"""
        if hook_input.trigger == "new_session":
            welcome_message = {
                "role": "system",
                "content": "Welcome to CktClaw! I'm ready to help you analyze circuits.",
            }
            return SessionStartHookResult(messages=[welcome_message])

        return SessionStartHookResult(messages=[])


class ContextRestorationHook(SessionStartHook):
    """上下文恢复钩子"""

    def __init__(self):
        super().__init__("context_restoration", priority=100)

    async def execute(
        self,
        hook_input: SessionStartHookInput,
        abort_signal: Optional[asyncio.Event] = None,
    ) -> SessionStartHookResult:
        """恢复会话上下文"""
        if hook_input.trigger == "compact":
            # 压缩后恢复上下文
            restoration_message = {
                "role": "system",
                "content": "Context has been compacted. Previous conversation is summarized above.",
            }
            return SessionStartHookResult(messages=[restoration_message])

        return SessionStartHookResult(messages=[])


# 全局钩子注册表
_registered_hooks: List[SessionStartHook] = [
    WelcomeMessageHook(),
    ContextRestorationHook(),
]


def register_session_start_hook(hook: SessionStartHook):
    """
    注册会话启动钩子

    Args:
        hook: 钩子实例
    """
    _registered_hooks.append(hook)
    # 按优先级排序
    _registered_hooks.sort(key=lambda h: h.priority)


def unregister_session_start_hook(name: str):
    """
    注销会话启动钩子

    Args:
        name: 钩子名称
    """
    global _registered_hooks
    _registered_hooks = [h for h in _registered_hooks if h.name != name]


async def execute_session_start_hooks(
    trigger: str,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    abort_signal: Optional[asyncio.Event] = None,
) -> List[Dict[str, Any]]:
    """
    执行所有会话启动钩子

    Args:
        trigger: 触发类型
        session_id: 会话 ID
        model: 模型名称
        abort_signal: 中止信号

    Returns:
        所有钩子生成的消息列表
    """
    hook_input = SessionStartHookInput(
        trigger=trigger,
        session_id=session_id,
        model=model,
    )

    all_messages = []

    for hook in _registered_hooks:
        # 检查是否中止
        if abort_signal and abort_signal.is_set():
            break

        try:
            result = await hook.execute(hook_input, abort_signal)

            # 收集消息
            if result.messages:
                all_messages.extend(result.messages)

        except Exception as e:
            # 钩子执行失败不应该阻止会话启动
            print(f"Warning: Session start hook '{hook.name}' failed: {e}")
            continue

    return all_messages
