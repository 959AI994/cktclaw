"""
Bootstrap State - 全局状态根基

参考 src/bootstrap/state.ts 实现 Python 版本的全局状态管理。

核心职责：
1. 管理全局状态（cwd, projectRoot, sessionId, modelUsage 等）
2. 提供原子操作接口（状态读写、计数器更新）
3. 线程安全的状态访问
4. 状态最小化原则

设计原则：
- DO NOT ADD MORE STATE HERE - BE JUDICIOUS WITH GLOBAL STATE
- 状态最小化，避免全局状态膨胀
- 使用 Pydantic 进行数据校验
- 使用 asyncio.Lock 保证线程安全
"""

import asyncio
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any
from uuid import uuid4
from pydantic import BaseModel, Field


class ModelUsage(BaseModel):
    """模型使用统计"""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


class BootstrapState(BaseModel):
    """全局状态（最小化原则）"""

    # 工作目录
    original_cwd: str = Field(default_factory=lambda: os.getcwd())
    project_root: str = Field(default_factory=lambda: os.getcwd())
    cwd: str = Field(default_factory=lambda: os.getcwd())

    # 会话信息
    session_id: str = Field(default_factory=lambda: uuid4().hex[:16])
    start_time: float = Field(default_factory=time.time)
    last_interaction_time: float = Field(default_factory=time.time)

    # 成本统计
    total_cost_usd: float = 0.0
    total_api_duration: float = 0.0
    total_api_duration_without_retries: float = 0.0
    total_tool_duration: float = 0.0

    # 轮次统计
    turn_hook_duration_ms: float = 0.0
    turn_tool_duration_ms: float = 0.0
    turn_classifier_duration_ms: float = 0.0
    turn_tool_count: int = 0
    turn_hook_count: int = 0
    turn_classifier_count: int = 0

    # 代码统计
    total_lines_added: int = 0
    total_lines_removed: int = 0

    # 模型使用
    model_usage: Dict[str, ModelUsage] = Field(default_factory=dict)
    has_unknown_model_cost: bool = False

    # 配置
    is_interactive: bool = True
    strict_tool_result_pairing: bool = False
    client_type: str = "cli"

    class Config:
        arbitrary_types_allowed = True


class StateManager:
    """
    全局状态管理器（单例模式）

    提供线程安全的状态访问和原子操作
    """

    _instance: Optional['StateManager'] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._state = BootstrapState()
            cls._instance._state_lock = asyncio.Lock()
        return cls._instance

    @property
    def state(self) -> BootstrapState:
        """获取当前状态（只读）"""
        return self._state

    async def get_session_id(self) -> str:
        """获取会话 ID"""
        async with self._state_lock:
            return self._state.session_id

    async def get_cwd(self) -> str:
        """获取当前工作目录"""
        async with self._state_lock:
            return self._state.cwd

    async def set_cwd(self, cwd: str) -> None:
        """设置当前工作目录"""
        async with self._state_lock:
            self._state.cwd = str(Path(cwd).resolve())

    async def get_project_root(self) -> str:
        """获取项目根目录"""
        async with self._state_lock:
            return self._state.project_root

    async def update_last_interaction_time(self) -> None:
        """更新最后交互时间"""
        async with self._state_lock:
            self._state.last_interaction_time = time.time()

    async def add_model_usage(
        self,
        model_name: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ) -> None:
        """添加模型使用统计"""
        async with self._state_lock:
            if model_name not in self._state.model_usage:
                self._state.model_usage[model_name] = ModelUsage()

            usage = self._state.model_usage[model_name]
            usage.input_tokens += input_tokens
            usage.output_tokens += output_tokens
            usage.cache_creation_input_tokens += cache_creation_input_tokens
            usage.cache_read_input_tokens += cache_read_input_tokens

    async def add_cost(self, cost_usd: float) -> None:
        """添加成本"""
        async with self._state_lock:
            self._state.total_cost_usd += cost_usd

    async def add_api_duration(self, duration: float, with_retries: bool = True) -> None:
        """添加 API 调用时长"""
        async with self._state_lock:
            self._state.total_api_duration += duration
            if not with_retries:
                self._state.total_api_duration_without_retries += duration

    async def add_tool_duration(self, duration: float) -> None:
        """添加工具执行时长"""
        async with self._state_lock:
            self._state.total_tool_duration += duration

    async def increment_turn_tool_count(self) -> None:
        """增加轮次工具计数"""
        async with self._state_lock:
            self._state.turn_tool_count += 1

    async def increment_turn_hook_count(self) -> None:
        """增加轮次钩子计数"""
        async with self._state_lock:
            self._state.turn_hook_count += 1

    async def reset_turn_counters(self) -> None:
        """重置轮次计数器"""
        async with self._state_lock:
            self._state.turn_hook_duration_ms = 0.0
            self._state.turn_tool_duration_ms = 0.0
            self._state.turn_classifier_duration_ms = 0.0
            self._state.turn_tool_count = 0
            self._state.turn_hook_count = 0
            self._state.turn_classifier_count = 0

    async def add_lines_changed(self, added: int, removed: int) -> None:
        """添加代码行数变更"""
        async with self._state_lock:
            self._state.total_lines_added += added
            self._state.total_lines_removed += removed

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        async with self._state_lock:
            return {
                "session_id": self._state.session_id,
                "uptime": time.time() - self._state.start_time,
                "total_cost_usd": self._state.total_cost_usd,
                "total_api_duration": self._state.total_api_duration,
                "total_tool_duration": self._state.total_tool_duration,
                "total_lines_added": self._state.total_lines_added,
                "total_lines_removed": self._state.total_lines_removed,
                "model_usage": {
                    name: usage.dict()
                    for name, usage in self._state.model_usage.items()
                },
            }

    def reset(self) -> None:
        """重置状态（仅用于测试）"""
        self._state = BootstrapState()


# 全局单例
_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """获取全局状态管理器单例"""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager


# 便捷函数
async def get_session_id() -> str:
    """获取会话 ID"""
    return await get_state_manager().get_session_id()


async def get_cwd() -> str:
    """获取当前工作目录"""
    return await get_state_manager().get_cwd()


async def set_cwd(cwd: str) -> None:
    """设置当前工作目录"""
    await get_state_manager().set_cwd(cwd)


async def get_project_root() -> str:
    """获取项目根目录"""
    return await get_state_manager().get_project_root()
