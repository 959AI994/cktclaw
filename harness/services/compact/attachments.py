"""
Post-compact file attachments — re-inject recently read files after trimming.

Helps the model avoid re-reading large files from disk when context was cut.
"""

from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from pathlib import Path
import asyncio


@dataclass
class FileAttachment:
    """Single restored file snapshot."""
    file_path: str
    content: str
    timestamp: float
    tokens: int


@dataclass
class AttachmentResult:
    """Batch of synthetic attachments plus accounting."""
    attachments: List[Dict[str, Any]]
    total_tokens: int
    files_restored: int


POST_COMPACT_MAX_FILES_TO_RESTORE = 5
POST_COMPACT_TOKEN_BUDGET = 50_000
POST_COMPACT_MAX_TOKENS_PER_FILE = 5_000


def estimate_file_tokens(content: str) -> int:
    """
    Rough token estimate from UTF-8 text length.

    Args:
        content: File text

    Returns:
        Approximate token count (~4 chars per token)
    """
    return len(content) // 4


def should_exclude_from_restore(file_path: str) -> bool:
    """
    Skip binary-ish, build, or VCS paths when restoring.

    Args:
        file_path: Absolute or relative path

    Returns:
        True if this path should not be re-attached
    """
    excluded_extensions = {
        ".db", ".sqlite", ".log", ".tmp",
        ".pyc", ".pyo", ".pyd",
        ".so", ".dll", ".dylib",
    }

    excluded_dirs = {
        "__pycache__", ".git", ".svn", ".hg",
        "node_modules", ".venv", "venv",
    }

    path = Path(file_path)

    if path.suffix.lower() in excluded_extensions:
        return True

    for part in path.parts:
        if part in excluded_dirs:
            return True

    return False


def collect_read_tool_file_paths(messages: List[Dict[str, Any]]) -> Set[str]:
    """
    Collect file_path targets from prior Read tool_calls in the transcript.

    Args:
        messages: Chat messages (assistant blocks with tool_calls)

    Returns:
        Set of resolved absolute paths already present in kept messages
    """
    file_paths = set()

    for message in messages:
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
                            except Exception:
                                continue
                        file_path = args.get("file_path")
                        if file_path:
                            file_paths.add(str(Path(file_path).resolve()))

    return file_paths


async def read_file_safe(file_path: str, max_tokens: int) -> Optional[str]:
    """
    Read text from disk with a byte cap derived from max_tokens.

    Args:
        file_path: Path to read
        max_tokens: Soft cap translated to bytes (~4 chars/token)

    Returns:
        File text or None on failure / missing file
    """
    try:
        path = Path(file_path)

        if not path.exists() or not path.is_file():
            return None

        file_size = path.stat().st_size
        max_bytes = max_tokens * 4

        if file_size > max_bytes:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(max_bytes)
                if len(content) >= max_bytes:
                    content = content[:max_bytes] + "\n\n[... file truncated for compaction]"
                return content
        else:
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
    Build attachment dicts from read_file_state after compaction.

    Args:
        read_file_state: Map of file_path -> {content, timestamp, ...}
        max_files: Max number of files to restore
        token_budget: Total token budget for all attachments
        max_tokens_per_file: Per-file read cap
        preserved_messages: Messages already kept (paths deduped)

    Returns:
        AttachmentResult with list payloads and totals
    """
    preserved_file_paths = set()
    if preserved_messages:
        preserved_file_paths = collect_read_tool_file_paths(preserved_messages)

    candidate_files = []

    for file_path, state in read_file_state.items():
        if should_exclude_from_restore(file_path):
            continue

        resolved_path = str(Path(file_path).resolve())
        if resolved_path in preserved_file_paths:
            continue

        candidate_files.append({
            "file_path": file_path,
            "timestamp": state.get("timestamp", 0),
            "content": state.get("content", ""),
        })

    candidate_files.sort(key=lambda f: f["timestamp"], reverse=True)

    candidate_files = candidate_files[:max_files]

    attachments = []
    total_tokens = 0
    files_restored = 0

    for file_info in candidate_files:
        file_path = file_info["file_path"]

        content = await read_file_safe(file_path, max_tokens_per_file)

        if content is None:
            continue

        file_tokens = estimate_file_tokens(content)

        if total_tokens + file_tokens > token_budget:
            remaining_budget = token_budget - total_tokens
            if remaining_budget < 1000:
                break

            max_chars = remaining_budget * 4
            content = content[:max_chars] + "\n\n[... file truncated due to token budget]"
            file_tokens = estimate_file_tokens(content)

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

        if total_tokens >= token_budget:
            break

    return AttachmentResult(
        attachments=attachments,
        total_tokens=total_tokens,
        files_restored=files_restored,
    )


def format_file_attachment_message(attachment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wrap one attachment dict as a synthetic user message.

    Args:
        attachment: create_post_compact_file_attachments entry

    Returns:
        User-role message suitable to append to the transcript
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
    High-level helper: build attachments then convert to user messages.

    Args:
        read_file_state: Same as create_post_compact_file_attachments
        preserved_messages: Dedup source

    Returns:
        List of user-shaped messages
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
