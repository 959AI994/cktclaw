"""
Auto Compact Service - 自动压缩服务

自动压缩逻辑。

核心功能：
1. Token 阈值检测
2. 自动触发压缩
3. 压缩失败重试
4. 压缩统计跟踪
"""

from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime


# 压缩配置常量
MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000
AUTOCOMPACT_BUFFER_TOKENS = 13_000
WARNING_THRESHOLD_BUFFER_TOKENS = 20_000
ERROR_THRESHOLD_BUFFER_TOKENS = 20_000
MANUAL_COMPACT_BUFFER_TOKENS = 3_000
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3


@dataclass
class AutoCompactTrackingState:
    """自动压缩跟踪状态"""
    compacted: bool = False
    turn_counter: int = 0
    turn_id: str = ""
    consecutive_failures: int = 0


@dataclass
class TokenWarningState:
    """Token 警告状态"""
    percent_left: float
    is_above_warning_threshold: bool
    is_above_error_threshold: bool
    is_above_auto_compact_threshold: bool


def get_effective_context_window_size(model: str) -> int:
    """
    获取有效上下文窗口大小

    Args:
        model: 模型名称

    Returns:
        有效上下文窗口大小（Token 数）
    """
    # 模型上下文窗口映射
    context_windows = {
        "claude-3-5-sonnet-20241022": 200_000,
        "claude-3-5-sonnet-20240620": 200_000,
        "claude-3-opus-20240229": 200_000,
        "claude-3-sonnet-20240229": 200_000,
        "claude-3-haiku-20240307": 200_000,
        "gpt-4": 8_000,
        "gpt-4-32k": 32_000,
        "gpt-3.5-turbo": 4_000,
        "deepseek-chat": 64_000,
    }

    context_window = context_windows.get(model, 200_000)

    # 减去输出预留空间
    reserved_tokens = min(MAX_OUTPUT_TOKENS_FOR_SUMMARY, 4_000)

    return context_window - reserved_tokens


def get_auto_compact_threshold(model: str) -> int:
    """
    获取自动压缩阈值

    Args:
        model: 模型名称

    Returns:
        自动压缩阈值（Token 数）
    """
    effective_window = get_effective_context_window_size(model)
    return effective_window - AUTOCOMPACT_BUFFER_TOKENS


def calculate_token_warning_state(
    token_usage: int,
    model: str
) -> TokenWarningState:
    """
    计算 Token 警告状态

    Args:
        token_usage: 当前 Token 使用量
        model: 模型名称

    Returns:
        Token 警告状态
    """
    effective_window = get_effective_context_window_size(model)
    auto_compact_threshold = get_auto_compact_threshold(model)
    warning_threshold = effective_window - WARNING_THRESHOLD_BUFFER_TOKENS
    error_threshold = effective_window - ERROR_THRESHOLD_BUFFER_TOKENS

    percent_left = max(0, (effective_window - token_usage) / effective_window * 100)

    return TokenWarningState(
        percent_left=percent_left,
        is_above_warning_threshold=token_usage >= warning_threshold,
        is_above_error_threshold=token_usage >= error_threshold,
        is_above_auto_compact_threshold=token_usage >= auto_compact_threshold,
    )


def is_auto_compact_enabled() -> bool:
    """检查自动压缩是否启用"""
    # 可以从环境变量或配置文件读取
    import os
    return os.environ.get("CKTCLAW_AUTO_COMPACT_ENABLED", "true").lower() == "true"


async def should_auto_compact(
    messages: List[Dict[str, Any]],
    model: str,
    tracking: Optional[AutoCompactTrackingState] = None,
    snip_tokens_freed: int = 0,
) -> bool:
    """
    判断是否应该触发自动压缩

    Args:
        messages: 消息列表
        model: 模型名称
        tracking: 压缩跟踪状态
        snip_tokens_freed: Snip 释放的 Token 数

    Returns:
        是否应该压缩
    """
    if not is_auto_compact_enabled():
        return False

    # 检查连续失败次数
    if tracking and tracking.consecutive_failures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES:
        return False

    # 估算当前 Token 数
    current_tokens = estimate_tokens(messages) - snip_tokens_freed

    # 获取阈值
    threshold = get_auto_compact_threshold(model)

    return current_tokens >= threshold


def estimate_tokens(messages: List[Dict[str, Any]]) -> int:
    """
    估算消息列表的 Token 数

    Args:
        messages: 消息列表

    Returns:
        估算的 Token 数
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            # 粗估：1 token ≈ 4 chars
            total += len(content) // 4
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "") or block.get("content", "")
                    total += len(str(text)) // 4

    # 保守系数
    return int(total * 4 / 3)


async def auto_compact(
    messages: List[Dict[str, Any]],
    model: str,
    tracking: Optional[AutoCompactTrackingState] = None,
    target_tokens: int = 40_000,
    llm_func: Optional[Any] = None,
    custom_instructions: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], int]:
    """
    执行自动压缩（完整实现）

    Args:
        messages: 消息列表
        model: 模型名称
        tracking: 压缩跟踪状态
        target_tokens: 目标 Token 数
        llm_func: LLM 调用函数（用于生成摘要）
        custom_instructions: 自定义压缩指令

    Returns:
        (压缩结果, 连续失败次数)
    """
    try:
        pre_compact_tokens = estimate_tokens(messages)

        # 1. 尝试 Session Memory Compact（最轻量）
        result = await _try_session_memory_compact(
            messages,
            target_tokens,
            pre_compact_tokens,
        )
        if result:
            return result, 0

        # 2. 尝试 Micro Compact（中等）
        result = await _try_micro_compact(
            messages,
            target_tokens,
            pre_compact_tokens,
        )
        if result:
            return result, 0

        # 3. Full Compact（需要 LLM）
        if llm_func:
            result = await _full_compact(
                messages,
                model,
                target_tokens,
                pre_compact_tokens,
                llm_func,
                custom_instructions,
            )
            if result:
                return result, 0

        # 4. 如果都失败，使用简单的后缀保留策略
        result = await _simple_suffix_compact(
            messages,
            target_tokens,
            pre_compact_tokens,
        )
        return result, 0

    except Exception as e:
        # 压缩失败，增加失败计数
        consecutive_failures = (tracking.consecutive_failures if tracking else 0) + 1
        return None, consecutive_failures


async def _try_session_memory_compact(
    messages: List[Dict[str, Any]],
    target_tokens: int,
    pre_compact_tokens: int,
) -> Optional[Dict[str, Any]]:
    """
    尝试 Session Memory 压缩

    策略：保留后缀消息，前缀依赖 session layer 语义
    """
    # 计算保留起点
    min_tokens = 10_000
    min_text_messages = 5

    kept_messages = []
    current_tokens = 0
    text_message_count = 0

    for msg in reversed(messages):
        msg_tokens = estimate_tokens([msg])

        # 统计文本消息
        if msg.get("role") in ["user", "assistant"]:
            text_message_count += 1

        kept_messages.insert(0, msg)
        current_tokens += msg_tokens

        # 检查是否满足最小要求
        if current_tokens >= min_tokens and text_message_count >= min_text_messages:
            break

    # 如果保留的消息太少，不适合 Session Memory Compact
    if len(kept_messages) >= len(messages) * 0.8:
        return None

    # 创建 boundary
    boundary = create_compact_boundary_message(
        pre_compact_tokens,
        current_tokens,
        "session_memory"
    )

    return {
        "boundary_marker": boundary,
        "summary_messages": [],  # Session Memory 不生成摘要
        "messages_to_keep": kept_messages,
        "pre_compact_token_count": pre_compact_tokens,
        "post_compact_token_count": current_tokens,
    }


async def _try_micro_compact(
    messages: List[Dict[str, Any]],
    target_tokens: int,
    pre_compact_tokens: int,
) -> Optional[Dict[str, Any]]:
    """
    尝试 Micro 压缩

    策略：清理工具结果中的冗长输出，不调用 LLM
    """
    from .micro_compact import micro_compact

    result = await micro_compact(
        messages,
        threshold_tokens=1000,
        preserve_recent_count=5,
    )

    # 检查是否节省了足够的 Token
    if result.tokens_saved < 5000:
        return None

    post_compact_tokens = pre_compact_tokens - result.tokens_saved

    boundary = create_compact_boundary_message(
        pre_compact_tokens,
        post_compact_tokens,
        "micro"
    )

    return {
        "boundary_marker": boundary,
        "summary_messages": [],
        "messages_to_keep": result.compacted_messages,
        "pre_compact_token_count": pre_compact_tokens,
        "post_compact_token_count": post_compact_tokens,
    }


async def _full_compact(
    messages: List[Dict[str, Any]],
    model: str,
    target_tokens: int,
    pre_compact_tokens: int,
    llm_func: Any,
    custom_instructions: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    完整压缩（调用 LLM 生成摘要）

    策略：
    1. 构造压缩 prompt
    2. 调用 LLM 生成摘要
    3. 创建 boundary 和 summary
    """
    # 构造压缩 prompt
    compact_prompt = _build_compact_prompt(custom_instructions)

    # 准备消息（去除图片和重复附件）
    from .micro_compact import strip_images_from_messages, strip_reinjected_attachments

    messages_to_summarize = strip_reinjected_attachments(
        strip_images_from_messages(messages)
    )

    # 添加压缩请求
    summary_request = {
        "role": "user",
        "content": compact_prompt,
    }

    # 调用 LLM
    try:
        summary_response = await llm_func(messages_to_summarize + [summary_request])

        # 提取摘要文本
        if isinstance(summary_response, dict):
            summary = summary_response.get("content", "")
        elif isinstance(summary_response, str):
            summary = summary_response
        else:
            return None

        if not summary or len(summary) < 50:
            return None

        # 创建 boundary 和 summary
        boundary = create_compact_boundary_message(
            pre_compact_tokens,
            estimate_tokens([{"role": "user", "content": summary}]),
            "auto"
        )

        summary_message = {
            "role": "user",
            "content": f"[Previous conversation summary]\n\n{summary}",
            "metadata": {
                "is_compact_summary": True,
            }
        }

        post_compact_tokens = estimate_tokens([boundary, summary_message])

        return {
            "boundary_marker": boundary,
            "summary_messages": [summary_message],
            "messages_to_keep": [],
            "pre_compact_token_count": pre_compact_tokens,
            "post_compact_token_count": post_compact_tokens,
        }

    except Exception as e:
        # LLM 调用失败，返回 None
        return None


async def _simple_suffix_compact(
    messages: List[Dict[str, Any]],
    target_tokens: int,
    pre_compact_tokens: int,
) -> Dict[str, Any]:
    """
    简单的后缀保留策略（兜底方案）

    策略：保留最近的消息，直到达到目标 Token 数
    """
    kept_messages = []
    current_tokens = 0

    for msg in reversed(messages):
        msg_tokens = estimate_tokens([msg])
        if current_tokens + msg_tokens > target_tokens:
            break
        kept_messages.insert(0, msg)
        current_tokens += msg_tokens

    boundary = create_compact_boundary_message(
        pre_compact_tokens,
        current_tokens,
        "simple"
    )

    return {
        "boundary_marker": boundary,
        "summary_messages": [],
        "messages_to_keep": kept_messages,
        "pre_compact_token_count": pre_compact_tokens,
        "post_compact_token_count": current_tokens,
    }


def _build_compact_prompt(custom_instructions: Optional[str] = None) -> str:
    """
    构造压缩 prompt

    Args:
        custom_instructions: 自定义指令

    Returns:
        压缩 prompt
    """
    base_prompt = """Please provide a concise summary of the conversation above.

Focus on:
1. Key decisions and conclusions
2. Important technical details
3. Action items and next steps
4. Critical context needed for future turns

Keep the summary under 500 words."""

    if custom_instructions:
        return f"{base_prompt}\n\nAdditional instructions:\n{custom_instructions}"

    return base_prompt


def create_compact_boundary_message(
    pre_compact_tokens: int,
    post_compact_tokens: int,
    compact_type: str = "auto"
) -> Dict[str, Any]:
    """
    创建压缩边界消息

    Args:
        pre_compact_tokens: 压缩前 Token 数
        post_compact_tokens: 压缩后 Token 数
        compact_type: 压缩类型

    Returns:
        压缩边界消息
    """
    return {
        "role": "system",
        "content": f"━━━ COMPACT BOUNDARY ━━━\n"
                  f"Previous conversation has been summarized.\n"
                  f"Pre-compact tokens: {pre_compact_tokens}\n"
                  f"Post-compact tokens: {post_compact_tokens}\n"
                  f"Tokens saved: {pre_compact_tokens - post_compact_tokens}\n"
                  f"Timestamp: {datetime.now().isoformat()}",
        "metadata": {
            "type": "compact_boundary",
            "pre_compact_tokens": pre_compact_tokens,
            "post_compact_tokens": post_compact_tokens,
            "tokens_saved": pre_compact_tokens - post_compact_tokens,
            "compact_type": compact_type,
        }
    }
