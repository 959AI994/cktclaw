"""
Auto-compact — threshold checks and tail-trim compaction for long transcripts.

1. Token usage vs model window
2. Optional auto-compact when over threshold
3. Failure counting (circuit breaker)
4. Lightweight accounting structs
"""

from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime


MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000
AUTOCOMPACT_BUFFER_TOKENS = 13_000
WARNING_THRESHOLD_BUFFER_TOKENS = 20_000
ERROR_THRESHOLD_BUFFER_TOKENS = 20_000
MANUAL_COMPACT_BUFFER_TOKENS = 3_000
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3


@dataclass
class AutoCompactTrackingState:
    """Per-session counters for compaction attempts."""
    compacted: bool = False
    turn_counter: int = 0
    turn_id: str = ""
    consecutive_failures: int = 0


@dataclass
class TokenWarningState:
    """UI-facing warning flags derived from usage vs window."""
    percent_left: float
    is_above_warning_threshold: bool
    is_above_error_threshold: bool
    is_above_auto_compact_threshold: bool


def get_effective_context_window_size(model: str) -> int:
    """
    Return usable context window minus a reserve for model output.

    Args:
        model: Provider model id string

    Returns:
        Approximate input token budget before hitting hard limits
    """
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

    reserved_tokens = min(MAX_OUTPUT_TOKENS_FOR_SUMMARY, 4_000)

    return context_window - reserved_tokens


def get_auto_compact_threshold(model: str) -> int:
    """
    Token estimate above which auto-compact should trigger.

    Args:
        model: Model id

    Returns:
        Threshold in estimated tokens
    """
    effective_window = get_effective_context_window_size(model)
    return effective_window - AUTOCOMPACT_BUFFER_TOKENS


def calculate_token_warning_state(
    token_usage: int,
    model: str
) -> TokenWarningState:
    """
    Derive warning / error / compact flags from current usage.

    Args:
        token_usage: Estimated prompt tokens so far
        model: Model id

    Returns:
        TokenWarningState for dashboards or logging
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
    """Return True unless CKTCLAW_AUTO_COMPACT_ENABLED is set to a falsey value."""
    import os
    return os.environ.get("CKTCLAW_AUTO_COMPACT_ENABLED", "true").lower() == "true"


async def should_auto_compact(
    messages: List[Dict[str, Any]],
    model: str,
    tracking: Optional[AutoCompactTrackingState] = None,
    snip_tokens_freed: int = 0,
) -> bool:
    """
    Decide whether to run compaction for this turn.

    Args:
        messages: Current transcript
        model: Model id for window lookup
        tracking: Optional failure counter state
        snip_tokens_freed: Tokens already reclaimed by snip-style trims

    Returns:
        True if compaction should run
    """
    if not is_auto_compact_enabled():
        return False

    if tracking and tracking.consecutive_failures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES:
        return False

    current_tokens = estimate_tokens(messages) - snip_tokens_freed

    threshold = get_auto_compact_threshold(model)

    return current_tokens >= threshold


def estimate_tokens(messages: List[Dict[str, Any]]) -> int:
    """
    Heuristic token count for a message list.

    Args:
        messages: Chat messages

    Returns:
        Inflated estimate (~4/3 multiplier)
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content) // 4
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "") or block.get("content", "")
                    total += len(str(text)) // 4

    return int(total * 4 / 3)


async def auto_compact(
    messages: List[Dict[str, Any]],
    model: str,
    tracking: Optional[AutoCompactTrackingState] = None,
    target_tokens: int = 40_000,
) -> Tuple[Optional[Dict[str, Any]], int]:
    """
    Tail-keep compaction: drop oldest messages until under target_tokens.

    Args:
        messages: Full transcript
        model: Unused today (reserved for model-specific strategies)
        tracking: Optional tracker for consecutive failures on error paths
        target_tokens: Desired post-compact estimated size

    Returns:
        (compaction_result dict, consecutive_failures) — failures increment on exception
    """
    try:
        pre_compact_tokens = estimate_tokens(messages)

        kept_messages = []
        current_tokens = 0

        for msg in reversed(messages):
            msg_tokens = estimate_tokens([msg])
            if current_tokens + msg_tokens > target_tokens:
                break
            kept_messages.insert(0, msg)
            current_tokens += msg_tokens

        boundary_message = {
            "role": "system",
            "content": f"━━━ COMPACT BOUNDARY ━━━\n"
                      f"Previous conversation has been summarized.\n"
                      f"Pre-compact tokens: {pre_compact_tokens}\n"
                      f"Post-compact tokens: {current_tokens}\n"
                      f"Timestamp: {datetime.now().isoformat()}",
            "metadata": {
                "type": "compact_boundary",
                "pre_compact_tokens": pre_compact_tokens,
                "post_compact_tokens": current_tokens,
                "compact_type": "auto",
            }
        }

        compaction_result = {
            "boundary_marker": boundary_message,
            "summary_messages": [],
            "messages_to_keep": kept_messages,
            "pre_compact_token_count": pre_compact_tokens,
            "post_compact_token_count": current_tokens,
        }

        consecutive_failures = 0

        return compaction_result, consecutive_failures

    except Exception:
        consecutive_failures = (tracking.consecutive_failures if tracking else 0) + 1
        return None, consecutive_failures


def create_compact_boundary_message(
    pre_compact_tokens: int,
    post_compact_tokens: int,
    compact_type: str = "auto"
) -> Dict[str, Any]:
    """
    Build a standalone compact_boundary system message.

    Args:
        pre_compact_tokens: Estimated size before compaction
        post_compact_tokens: Estimated size after compaction
        compact_type: Label stored in metadata

    Returns:
        System-role message dict
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
