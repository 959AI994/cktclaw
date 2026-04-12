"""
Micro-compact — trim bulky tool outputs without calling an LLM.

1. Shorten or clear oversized tool_result payloads
2. Keep tool_use / structure intact
3. No summarization model call (cheap path)
"""

from typing import List, Dict, Any, Set, Optional
from dataclasses import dataclass


# Tools whose outputs may be aggressively trimmed
COMPACTABLE_TOOLS = {
    "Read",
    "Bash",
    "Grep",
    "Glob",
    "WebSearch",
    "WebFetch",
    "Edit",
    "Write",
    # EDA backends
    "abc",
    "yosys",
    "reverse",
    "opensta",
}

TIME_BASED_MC_CLEARED_MESSAGE = "[Old tool result content cleared]"

IMAGE_MAX_TOKEN_SIZE = 2000


@dataclass
class MicroCompactResult:
    """Outcome of a micro-compact pass."""
    messages: List[Dict[str, Any]]
    tokens_saved: int = 0
    tools_compacted: int = 0
    compaction_info: Optional[Dict[str, Any]] = None


def should_compact_tool(tool_name: str) -> bool:
    """
    Return True if this tool's outputs are eligible for trimming.

    Args:
        tool_name: Tool identifier from the provider

    Returns:
        Whether micro-compact may rewrite its tool_result rows
    """
    return tool_name in COMPACTABLE_TOOLS


def estimate_tool_result_tokens(content: str) -> int:
    """
    Rough token estimate for a tool_result string body.

    Args:
        content: Serialized tool output

    Returns:
        Approximate tokens (~4 chars per token)
    """
    return len(content) // 4


def should_clear_tool_result(
    tool_name: str,
    content: str,
    threshold_tokens: int = 1000
) -> bool:
    """
    Decide whether a single tool_result is large enough to clear.

    Args:
        tool_name: Tool name on the tool message
        content: tool_result text
        threshold_tokens: Minimum estimated tokens before clearing

    Returns:
        True if the row should be replaced with TIME_BASED_MC_CLEARED_MESSAGE
    """
    if not should_compact_tool(tool_name):
        return False

    tokens = estimate_tool_result_tokens(content)
    return tokens > threshold_tokens


def clear_tool_result(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Replace tool_result body with a short placeholder and set metadata.

    Args:
        message: Original tool-role message

    Returns:
        Shallow-copied message with cleared content
    """
    cleared_message = message.copy()

    cleared_message["content"] = TIME_BASED_MC_CLEARED_MESSAGE

    if "metadata" not in cleared_message:
        cleared_message["metadata"] = {}
    cleared_message["metadata"]["microcompacted"] = True

    return cleared_message


async def micro_compact(
    messages: List[Dict[str, Any]],
    threshold_tokens: int = 1000,
    preserve_recent_count: int = 5
) -> MicroCompactResult:
    """
    Walk messages and clear oversized tool rows outside the protected tail.

    Args:
        messages: Full transcript
        threshold_tokens: Per-tool_result size threshold
        preserve_recent_count: Do not touch the last N messages

    Returns:
        MicroCompactResult with rewritten list and savings estimate
    """
    compacted_messages = []
    tokens_saved = 0
    tools_compacted = 0

    protected_start_index = max(0, len(messages) - preserve_recent_count)

    for i, msg in enumerate(messages):
        if i >= protected_start_index:
            compacted_messages.append(msg)
            continue

        if msg.get("role") != "tool":
            compacted_messages.append(msg)
            continue

        tool_name = msg.get("name", "")
        content = msg.get("content", "")

        if should_clear_tool_result(tool_name, content, threshold_tokens):
            original_tokens = estimate_tool_result_tokens(content)
            cleared_tokens = estimate_tool_result_tokens(TIME_BASED_MC_CLEARED_MESSAGE)
            tokens_saved += original_tokens - cleared_tokens

            cleared_msg = clear_tool_result(msg)
            compacted_messages.append(cleared_msg)
            tools_compacted += 1
        else:
            compacted_messages.append(msg)

    return MicroCompactResult(
        messages=compacted_messages,
        tokens_saved=tokens_saved,
        tools_compacted=tools_compacted,
        compaction_info={
            "type": "micro",
            "threshold_tokens": threshold_tokens,
            "preserve_recent_count": preserve_recent_count,
        }
    )


def create_microcompact_boundary_message(
    tokens_saved: int,
    tools_compacted: int
) -> Dict[str, Any]:
    """
    Build a synthetic system marker after micro-compact.

    Args:
        tokens_saved: Estimated tokens reclaimed
        tools_compacted: Number of tool rows cleared

    Returns:
        System-style dict suitable to append to the transcript
    """
    return {
        "role": "system",
        "content": f"━━━ MICRO COMPACT ━━━\n"
                  f"Cleared {tools_compacted} old tool results.\n"
                  f"Tokens saved: ~{tokens_saved}",
        "metadata": {
            "type": "microcompact_boundary",
            "tokens_saved": tokens_saved,
            "tools_compacted": tools_compacted,
        }
    }


async def try_micro_compact(
    messages: List[Dict[str, Any]],
    min_tokens_to_save: int = 5000
) -> Optional[MicroCompactResult]:
    """
    Run micro_compact and discard the result if savings are below min_tokens_to_save.

    Args:
        messages: Transcript
        min_tokens_to_save: Minimum delta required to treat compaction as useful

    Returns:
        MicroCompactResult or None if savings were too small
    """
    result = await micro_compact(messages)

    if result.tokens_saved >= min_tokens_to_save:
        return result

    return None
