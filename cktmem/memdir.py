"""
CktMem Memory Directory - 记忆目录管理

参考 Claude Code 的 memdir.ts 实现
负责加载、格式化、截断记忆内容
"""

import os
from pathlib import Path
from typing import Optional, Tuple

from .paths import (
    get_auto_mem_path,
    is_auto_memory_enabled,
    ENTRYPOINT_NAME,
    MAX_ENTRYPOINT_LINES,
    MAX_ENTRYPOINT_BYTES,
)
from .memory_types import build_memory_guidelines


def truncate_entrypoint_content(raw: str) -> Tuple[str, int, int, bool, bool]:
    """
    截断 MEMORY.md 内容到行数和字节限制

    Args:
        raw: 原始内容

    Returns:
        (截断后内容, 行数, 字节数, 是否行截断, 是否字节截断)
    """
    trimmed = raw.strip()
    content_lines = trimmed.split('\n')
    line_count = len(content_lines)
    byte_count = len(trimmed.encode('utf-8'))

    was_line_truncated = line_count > MAX_ENTRYPOINT_LINES
    was_byte_truncated = byte_count > MAX_ENTRYPOINT_BYTES

    if not was_line_truncated and not was_byte_truncated:
        return trimmed, line_count, byte_count, False, False

    # 先按行截断
    truncated = '\n'.join(content_lines[:MAX_ENTRYPOINT_LINES]) if was_line_truncated else trimmed

    # 再按字节截断
    if len(truncated.encode('utf-8')) > MAX_ENTRYPOINT_BYTES:
        # 找到最后一个换行符，避免截断到行中间
        truncated_bytes = truncated.encode('utf-8')[:MAX_ENTRYPOINT_BYTES]
        try:
            truncated = truncated_bytes.decode('utf-8', errors='ignore')
            last_newline = truncated.rfind('\n')
            if last_newline > 0:
                truncated = truncated[:last_newline]
        except:
            pass

    # 添加警告
    reason = ""
    if was_byte_truncated and not was_line_truncated:
        reason = f"{byte_count} bytes (limit: {MAX_ENTRYPOINT_BYTES}) — index entries are too long"
    elif was_line_truncated and not was_byte_truncated:
        reason = f"{line_count} lines (limit: {MAX_ENTRYPOINT_LINES})"
    else:
        reason = f"{line_count} lines and {byte_count} bytes"

    warning = f"\n\n> WARNING: {ENTRYPOINT_NAME} is {reason}. Only part of it was loaded. Keep index entries to one line under ~200 chars; move detail into topic files."

    return truncated + warning, line_count, byte_count, was_line_truncated, was_byte_truncated


def ensure_memory_dir_exists(memory_dir: str):
    """
    确保记忆目录存在

    Args:
        memory_dir: 记忆目录路径
    """
    Path(memory_dir).mkdir(parents=True, exist_ok=True)


def load_memory_prompt(project_root: Optional[str] = None, skip_index: bool = False) -> Optional[str]:
    """
    加载记忆提示词

    Args:
        project_root: 项目根目录（可选）
        skip_index: 是否跳过索引模式

    Returns:
        记忆提示词文本，如果禁用则返回 None
    """
    if not is_auto_memory_enabled():
        return None

    memory_dir = get_auto_mem_path(project_root)
    ensure_memory_dir_exists(memory_dir)

    # 构建指南
    guidelines = build_memory_guidelines(memory_dir, skip_index)

    # 读取 MEMORY.md（如果存在）
    entrypoint_path = Path(memory_dir) / ENTRYPOINT_NAME
    entrypoint_content = ""

    if entrypoint_path.exists():
        try:
            with open(entrypoint_path, 'r', encoding='utf-8') as f:
                entrypoint_content = f.read()
        except Exception as e:
            print(f"Warning: Failed to read {ENTRYPOINT_NAME}: {e}")

    # 如果有内容，截断并添加
    if entrypoint_content.strip():
        truncated, line_count, byte_count, was_line_truncated, was_byte_truncated = \
            truncate_entrypoint_content(entrypoint_content)

        guidelines.extend([
            "",
            "## Current Memory Index",
            "",
            truncated,
        ])

        # 日志记录（可选）
        if was_line_truncated or was_byte_truncated:
            print(f"Memory index truncated: {line_count} lines, {byte_count} bytes")

    return "\n".join(guidelines)


def format_memory_size(size_bytes: int) -> str:
    """
    格式化文件大小

    Args:
        size_bytes: 字节数

    Returns:
        格式化的大小字符串
    """
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


if __name__ == "__main__":
    # 测试记忆加载
    print("CktMem Memory Directory 测试")
    print("=" * 60)

    memory_dir = get_auto_mem_path()
    print(f"记忆目录: {memory_dir}")

    # 确保目录存在
    ensure_memory_dir_exists(memory_dir)

    # 创建测试 MEMORY.md
    test_content = """# Memory Index

- [User Background](user_background.md) — EDA engineer focusing on ASAP7
- [Project Goals](project_goals.md) — Low-power RISC-V CPU design
- [Circuit Adder](circuit_adder.md) — 8-bit adder analysis
"""

    entrypoint_path = Path(memory_dir) / ENTRYPOINT_NAME
    with open(entrypoint_path, 'w', encoding='utf-8') as f:
        f.write(test_content)

    print(f"✓ 创建测试 {ENTRYPOINT_NAME}")

    # 加载记忆提示词
    prompt = load_memory_prompt()
    if prompt:
        print(f"\n记忆提示词长度: {len(prompt)} 字符")
        print("\n前 500 字符:")
        print(prompt[:500])
    else:
        print("记忆系统已禁用")

    print("\n" + "=" * 60)
