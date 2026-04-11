"""
Attachments - 文件附件恢复

在压缩后恢复最近访问的文件，避免模型重新读取。
"""

from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from pathlib import Path
import asyncio


@dataclass
class FileAttachment:
    """文件附件"""
    file_path: str
    content: str
    timestamp: float
    tokens: int


@dataclass
class AttachmentResult:
    """附件结果"""
    attachments: List[Dict[str, Any]]
    total_tokens: int
    files_restored: int


# 配置常量
POST_COMPACT_MAX_FILES_TO_RESTORE = 5
POST_COMPACT_TOKEN_BUDGET = 50_000
POST_COMPACT_MAX_TOKENS_PER_FILE = 5_000


def estimate_file_tokens(content: str) -> int:
    """
    估算文件内容的 Token 数

    Args:
        content: 文件内容

    Returns:
        估算的 Token 数
    """
    # 粗估：1 token ≈ 4 chars
    return len(content) // 4


def should_exclude_from_restore(file_path: str) -> bool:
    """
    判断文件是否应该排除在恢复之外

    Args:
        file_path: 文件路径

    Returns:
        是否应该排除
    """
    # 排除的文件类型
    excluded_extensions = {
        ".db", ".sqlite", ".log", ".tmp",
        ".pyc", ".pyo", ".pyd",
        ".so", ".dll", ".dylib",
    }

    # 排除的目录
    excluded_dirs = {
        "__pycache__", ".git", ".svn", ".hg",
        "node_modules", ".venv", "venv",
    }

    path = Path(file_path)

    # 检查扩展名
    if path.suffix.lower() in excluded_extensions:
        return True

    # 检查目录
    for part in path.parts:
        if part in excluded_dirs:
            return True

    return False


def collect_read_tool_file_paths(messages: List[Dict[str, Any]]) -> Set[str]:
    """
    从消息中收集已读取的文件路径

    Args:
        messages: 消息列表

    Returns:
        文件路径集合
    """
    file_paths = set()

    for message in messages:
        # 检查工具调用
        if message.get("role") == "assistant":
            tool_calls = message.get("tool_calls", [])
            for tool_call in tool_calls:
                if isinstance(tool_call, dict):
                    function = tool_call.get("function", {})
                    if function.get("name") == "Read":
                        args = function.get("arguments", {})
                        if isinstance(args, str):
                            import json
                            try:
                                args = json.loads(args)
                            except:
                                continue
                        file_path = args.get("file_path")
                        if file_path:
                            file_paths.add(str(Path(file_path).resolve()))

    return file_paths


async def read_file_safe(file_path: str, max_tokens: int) -> Optional[str]:
    """
    安全地读取文件

    Args:
        file_path: 文件路径
        max_tokens: 最大 Token 数

    Returns:
        文件内容（如果成功）
    """
    try:
        path = Path(file_path)

        if not path.exists() or not path.is_file():
            return None

        # 检查文件大小
        file_size = path.stat().st_size
        max_bytes = max_tokens * 4  # 粗估

        if file_size > max_bytes:
            # 文件太大，只读取前面部分
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(max_bytes)
                if len(content) >= max_bytes:
                    content = content[:max_bytes] + "\n\n[... file truncated for compaction]"
                return content
        else:
            # 读取完整文件
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()

    except Exception as e:
        print(f"Warning: Failed to read file {file_path}: {e}")
        return None


async def create_post_compact_file_attachments(
    read_file_state: Dict[str, Dict[str, Any]],
    max_files: int = POST_COMPACT_MAX_FILES_TO_RESTORE,
    token_budget: int = POST_COMPACT_TOKEN_BUDGET,
    max_tokens_per_file: int = POST_COMPACT_MAX_TOKENS_PER_FILE,
    preserved_messages: Optional[List[Dict[str, Any]]] = None,
) -> AttachmentResult:
    """
    创建压缩后的文件附件

    参考 compact.ts:1415-1464

    Args:
        read_file_state: 文件状态字典 {file_path: {content, timestamp}}
        max_files: 最大恢复文件数
        token_budget: Token 预算
        max_tokens_per_file: 每个文件的最大 Token 数
        preserved_messages: 保留的消息（用于去重）

    Returns:
        附件结果
    """
    # 收集已经在保留消息中的文件路径
    preserved_file_paths = set()
    if preserved_messages:
        preserved_file_paths = collect_read_tool_file_paths(preserved_messages)

    # 过滤和排序文件
    candidate_files = []

    for file_path, state in read_file_state.items():
        # 排除不应该恢复的文件
        if should_exclude_from_restore(file_path):
            continue

        # 排除已经在保留消息中的文件
        resolved_path = str(Path(file_path).resolve())
        if resolved_path in preserved_file_paths:
            continue

        candidate_files.append({
            "file_path": file_path,
            "timestamp": state.get("timestamp", 0),
            "content": state.get("content", ""),
        })

    # 按时间戳排序（最近的优先）
    candidate_files.sort(key=lambda f: f["timestamp"], reverse=True)

    # 限制文件数量
    candidate_files = candidate_files[:max_files]

    # 创建附件
    attachments = []
    total_tokens = 0
    files_restored = 0

    for file_info in candidate_files:
        file_path = file_info["file_path"]

        # 读取文件（限制大小）
        content = await read_file_safe(file_path, max_tokens_per_file)

        if content is None:
            continue

        # 估算 Token 数
        file_tokens = estimate_file_tokens(content)

        # 检查是否超出预算
        if total_tokens + file_tokens > token_budget:
            # 尝试截断内容
            remaining_budget = token_budget - total_tokens
            if remaining_budget < 1000:  # 预算不足，跳过
                break

            # 截断内容
            max_chars = remaining_budget * 4
            content = content[:max_chars] + "\n\n[... file truncated due to token budget]"
            file_tokens = estimate_file_tokens(content)

        # 创建附件
        attachment = {
            "type": "file_attachment",
            "file_path": file_path,
            "content": content,
            "tokens": file_tokens,
            "timestamp": file_info["timestamp"],
        }

        attachments.append(attachment)
        total_tokens += file_tokens
        files_restored += 1

        # 检查是否达到预算
        if total_tokens >= token_budget:
            break

    return AttachmentResult(
        attachments=attachments,
        total_tokens=total_tokens,
        files_restored=files_restored,
    )


def format_file_attachment_message(attachment: Dict[str, Any]) -> Dict[str, Any]:
    """
    格式化文件附件为消息

    Args:
        attachment: 附件字典

    Returns:
        消息字典
    """
    file_path = attachment["file_path"]
    content = attachment["content"]

    return {
        "role": "user",
        "content": f"[File restored from cache: {file_path}]\n\n```\n{content}\n```",
        "metadata": {
            "type": "file_attachment",
            "file_path": file_path,
            "is_post_compact_restoration": True,
        }
    }


async def create_and_format_file_attachments(
    read_file_state: Dict[str, Dict[str, Any]],
    preserved_messages: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    创建并格式化文件附件为消息列表

    Args:
        read_file_state: 文件状态字典
        preserved_messages: 保留的消息

    Returns:
        消息列表
    """
    result = await create_post_compact_file_attachments(
        read_file_state=read_file_state,
        preserved_messages=preserved_messages,
    )

    messages = []
    for attachment in result.attachments:
        message = format_file_attachment_message(attachment)
        messages.append(message)

    return messages
