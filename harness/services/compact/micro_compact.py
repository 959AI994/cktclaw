"""
Micro Compact Service - 微压缩服务

参考 Claude Code 的 compact.ts 实现微压缩逻辑。

核心功能：
1. 清理工具结果中的冗长输出
2. 保留工具调用本身
3. 不生成 LLM 摘要（轻量级压缩）
4. 清理图片和文档块
5. 清理重复附件
"""

from typing import List, Dict, Any, Set, Optional
from dataclasses import dataclass
import copy


# 可压缩的工具列表
COMPACTABLE_TOOLS = {
    "Read",
    "Bash",
    "Grep",
    "Glob",
    "WebSearch",
    "WebFetch",
    "Edit",
    "Write",
    # EDA 工具
    "abc",
    "yosys",
    "reverse",
    "opensta",
}

# 清理消息
TIME_BASED_MC_CLEARED_MESSAGE = "[Old tool result content cleared]"

# 图像最大 Token 大小
IMAGE_MAX_TOKEN_SIZE = 2000


@dataclass
class MicroCompactResult:
    """微压缩结果"""
    compacted_messages: List[Dict[str, Any]]
    tokens_saved: int = 0
    tools_compacted: int = 0
    compaction_info: Optional[Dict[str, Any]] = None


def should_compact_tool(tool_name: str) -> bool:
    """
    判断工具是否应该被压缩

    Args:
        tool_name: 工具名称

    Returns:
        是否应该压缩
    """
    return tool_name in COMPACTABLE_TOOLS


def estimate_tool_result_tokens(content: str) -> int:
    """
    估算工具结果的 Token 数

    Args:
        content: 工具结果内容

    Returns:
        估算的 Token 数
    """
    # 粗估：1 token ≈ 4 chars
    return len(content) // 4


def should_clear_tool_result(
    tool_name: str,
    content: str,
    threshold_tokens: int = 1000
) -> bool:
    """
    判断是否应该清理工具结果

    Args:
        tool_name: 工具名称
        content: 工具结果内容
        threshold_tokens: Token 阈值

    Returns:
        是否应该清理
    """
    if not should_compact_tool(tool_name):
        return False

    tokens = estimate_tool_result_tokens(content)
    return tokens > threshold_tokens


def clear_tool_result(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    清理工具结果内容

    Args:
        message: 工具结果消息

    Returns:
        清理后的消息
    """
    cleared_message = message.copy()

    # 替换内容为清理消息
    cleared_message["content"] = TIME_BASED_MC_CLEARED_MESSAGE

    # 添加元数据标记
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
    执行微压缩

    Args:
        messages: 消息列表
        threshold_tokens: Token 阈值
        preserve_recent_count: 保留最近 N 条消息不压缩

    Returns:
        微压缩结果
    """
    compacted_messages = []
    tokens_saved = 0
    tools_compacted = 0

    # 计算需要保护的消息索引
    protected_start_index = max(0, len(messages) - preserve_recent_count)

    for i, msg in enumerate(messages):
        # 保护最近的消息
        if i >= protected_start_index:
            compacted_messages.append(msg)
            continue

        # 只处理工具结果消息
        if msg.get("role") != "tool":
            compacted_messages.append(msg)
            continue

        tool_name = msg.get("name", "")
        content = msg.get("content", "")

        # 检查是否应该清理
        if should_clear_tool_result(tool_name, content, threshold_tokens):
            # 估算节省的 Token
            original_tokens = estimate_tool_result_tokens(content)
            cleared_tokens = estimate_tool_result_tokens(TIME_BASED_MC_CLEARED_MESSAGE)
            tokens_saved += original_tokens - cleared_tokens

            # 清理消息
            cleared_msg = clear_tool_result(msg)
            compacted_messages.append(cleared_msg)
            tools_compacted += 1
        else:
            compacted_messages.append(msg)

    return MicroCompactResult(
        compacted_messages=compacted_messages,
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
    创建微压缩边界消息

    Args:
        tokens_saved: 节省的 Token 数
        tools_compacted: 压缩的工具数

    Returns:
        微压缩边界消息
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
    尝试执行微压缩

    Args:
        messages: 消息列表
        min_tokens_to_save: 最小节省 Token 数阈值

    Returns:
        微压缩结果（如果节省的 Token 足够多）
    """
    result = await micro_compact(messages)

    # 只有节省足够多的 Token 才返回结果
    if result.tokens_saved >= min_tokens_to_save:
        return result

    return None


def strip_images_from_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    清理消息中的图片和文档块

    参考 compact.ts:145-200

    策略：
    1. 用户消息中的图片块 → [image]
    2. 文档块 → [document]
    3. tool_result 中嵌套的图片/文档

    Args:
        messages: 消息列表

    Returns:
        清理后的消息列表
    """
    cleaned_messages = []

    for message in messages:
        # 只处理用户消息
        if message.get("role") != "user":
            cleaned_messages.append(message)
            continue

        content = message.get("content")

        # 如果不是数组，直接保留
        if not isinstance(content, list):
            cleaned_messages.append(message)
            continue

        # 处理内容块
        has_media_block = False
        new_content = []

        for block in content:
            if not isinstance(block, dict):
                new_content.append(block)
                continue

            block_type = block.get("type")

            # 图片块 → [image]
            if block_type == "image":
                has_media_block = True
                new_content.append({"type": "text", "text": "[image]"})
                continue

            # 文档块 → [document]
            if block_type == "document":
                has_media_block = True
                new_content.append({"type": "text", "text": "[document]"})
                continue

            # 处理 tool_result 中嵌套的图片/文档
            if block_type == "tool_result" and isinstance(block.get("content"), list):
                tool_has_media = False
                new_tool_content = []

                for item in block["content"]:
                    if not isinstance(item, dict):
                        new_tool_content.append(item)
                        continue

                    item_type = item.get("type")

                    if item_type == "image":
                        tool_has_media = True
                        new_tool_content.append({"type": "text", "text": "[image]"})
                    elif item_type == "document":
                        tool_has_media = True
                        new_tool_content.append({"type": "text", "text": "[document]"})
                    else:
                        new_tool_content.append(item)

                if tool_has_media:
                    has_media_block = True
                    new_block = copy.deepcopy(block)
                    new_block["content"] = new_tool_content
                    new_content.append(new_block)
                else:
                    new_content.append(block)
            else:
                new_content.append(block)

        # 如果没有媒体块，保留原消息
        if not has_media_block:
            cleaned_messages.append(message)
        else:
            # 创建新消息
            new_message = copy.deepcopy(message)
            new_message["content"] = new_content
            cleaned_messages.append(new_message)

    return cleaned_messages


def strip_reinjected_attachments(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    清理会被重新注入的附件

    参考 compact.ts:211-223

    策略：
    - 移除 skill_discovery 和 skill_listing 附件
    - 这些附件会在压缩后重新注入，不需要发送给 LLM

    Args:
        messages: 消息列表

    Returns:
        清理后的消息列表
    """
    cleaned_messages = []

    for message in messages:
        # 检查是否是附件消息
        if message.get("type") == "attachment":
            attachment_type = message.get("attachment", {}).get("type")

            # 跳过会被重新注入的附件
            if attachment_type in ["skill_discovery", "skill_listing"]:
                continue

        cleaned_messages.append(message)

    return cleaned_messages


@dataclass
class MicroCompactResult:
    """微压缩结果（更新版）"""
    compacted_messages: List[Dict[str, Any]]
    tokens_saved: int = 0
    tools_compacted: int = 0
    compaction_info: Optional[Dict[str, Any]] = None
