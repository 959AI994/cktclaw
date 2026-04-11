"""
Query Types - 查询循环类型定义

参考 src/query.ts 实现 Python 版本的查询循环系统。

核心职责：
1. 定义查询状态（QueryState）
2. 定义转换类型（Continue/Terminal）
3. 定义查询配置（QueryConfig）
4. 定义查询结果（QueryResult）

设计原则：
- 状态机驱动（Continue/Terminal）
- 不可变状态（每次迭代创建新状态）
- 错误恢复（max_output_tokens 等）
- 预算管理（Token 预算跟踪）
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TransitionType(str, Enum):
    """转换类型"""
    CONTINUE = "continue"  # 继续循环
    TERMINAL = "terminal"  # 终止循环


class ContinueReason(str, Enum):
    """继续原因"""
    TOOL_USE = "tool_use"                      # 工具调用
    MAX_OUTPUT_TOKENS = "max_output_tokens"    # 输出 Token 超限
    REACTIVE_COMPACT = "reactive_compact"      # 响应式压缩
    AUTO_COMPACT = "auto_compact"              # 自动压缩
    BUDGET_CONTINUATION = "budget_continuation"  # 预算继续


class TerminalReason(str, Enum):
    """终止原因"""
    END_TURN = "end_turn"              # 正常结束
    MAX_TURNS = "max_turns"            # 达到最大轮次
    BUDGET_EXCEEDED = "budget_exceeded"  # 预算超限
    ERROR = "error"                    # 错误
    USER_INTERRUPT = "user_interrupt"  # 用户中断


class AutoCompactTracking(BaseModel):
    """自动压缩跟踪"""
    consecutive_failures: int = 0
    last_attempt_tokens: int = 0
    last_attempt_time: Optional[datetime] = None


class QueryState(BaseModel):
    """
    查询循环状态

    在每次迭代之间传递的可变状态
    """
    # 消息列表
    messages: List[Dict[str, Any]] = Field(default_factory=list)

    # 工具使用上下文
    tool_use_context: Dict[str, Any] = Field(default_factory=dict)

    # 自动压缩跟踪
    auto_compact_tracking: Optional[AutoCompactTracking] = None

    # max_output_tokens 恢复计数
    max_output_tokens_recovery_count: int = 0

    # 是否尝试过响应式压缩
    has_attempted_reactive_compact: bool = False

    # max_output_tokens 覆盖值
    max_output_tokens_override: Optional[int] = None

    # 停止钩子是否激活
    stop_hook_active: Optional[bool] = None

    # 轮次计数
    turn_count: int = 1

    # 上一次转换原因
    transition: Optional[ContinueReason] = None

    class Config:
        arbitrary_types_allowed = True


class QueryConfig(BaseModel):
    """查询配置"""
    # 系统 Prompt
    system_prompt: str

    # 用户上下文
    user_context: Dict[str, str] = Field(default_factory=dict)

    # 系统上下文
    system_context: Dict[str, str] = Field(default_factory=dict)

    # 最大轮次
    max_turns: Optional[int] = None

    # 最大预算（USD）
    max_budget_usd: Optional[float] = None

    # Token 预算
    token_budget: Optional[int] = None

    # 自动压缩阈值
    auto_compact_threshold: int = 150_000

    # 目标 Token 数
    target_tokens: int = 40_000

    # 是否启用自动压缩
    auto_compact_enabled: bool = True

    # 是否启用响应式压缩
    reactive_compact_enabled: bool = False

    # 是否跳过缓存写入
    skip_cache_write: bool = False

    # 查询来源
    query_source: str = "unknown"


class QueryResult(BaseModel):
    """查询结果"""
    # 终止原因
    terminal_reason: TerminalReason

    # 最终消息列表
    messages: List[Dict[str, Any]] = Field(default_factory=list)

    # 总轮次
    total_turns: int = 0

    # 总 Token 使用
    total_tokens: int = 0

    # 总成本（USD）
    total_cost: float = 0.0

    # 工具调用次数
    tool_calls: int = 0

    # 压缩次数
    compactions: int = 0

    # 错误信息
    error: Optional[str] = None

    # 创建时间
    created_at: datetime = Field(default_factory=datetime.now)


class ToolUseBlock(BaseModel):
    """工具使用块"""
    id: str
    type: str = "tool_use"
    name: str
    input: Dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    """工具结果块"""
    type: str = "tool_result"
    tool_use_id: str
    content: str
    is_error: bool = False


def validate_tool_result_pairing(messages: List[Dict[str, Any]]) -> List[str]:
    """
    验证 Tool-Result 配对

    检查每个 tool_use 是否都有对应的 tool_result

    Args:
        messages: 消息列表

    Returns:
        缺失的 tool_use_id 列表
    """
    tool_use_ids = set()
    tool_result_ids = set()

    for msg in messages:
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_use_ids.add(block.get("id"))

        if msg.get("role") == "user":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_result_ids.add(block.get("tool_use_id"))

    # 找出缺失的 tool_result
    missing = tool_use_ids - tool_result_ids
    return list(missing)


def create_missing_tool_results(
    missing_ids: List[str],
    error_message: str = "Tool execution was interrupted",
) -> List[Dict[str, Any]]:
    """
    为缺失的 tool_use 创建错误 tool_result

    Args:
        missing_ids: 缺失的 tool_use_id 列表
        error_message: 错误消息

    Returns:
        tool_result 消息列表
    """
    results = []
    for tool_use_id in missing_ids:
        results.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": error_message,
                    "is_error": True,
                }
            ],
        })
    return results
