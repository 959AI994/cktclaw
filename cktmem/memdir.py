"""
CktMem memory directory — load, truncate, and format the MEMORY.md index.

Ensures the on-disk tree exists, stitches guidelines with the live index, and
applies byte/line caps so prompts stay bounded.
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
    Clamp MEMORY.md to ``MAX_ENTRYPOINT_LINES`` and ``MAX_ENTRYPOINT_BYTES``.

    Args:
        raw: Full index file contents.

    Returns:
        Tuple of ``(truncated_text, line_count, byte_count, line_truncated, byte_truncated)``.
    """
    trimmed = raw.strip()
    content_lines = trimmed.split('\n')
    line_count = len(content_lines)
    byte_count = len(trimmed.encode('utf-8'))

    was_line_truncated = line_count > MAX_ENTRYPOINT_LINES
    was_byte_truncated = byte_count > MAX_ENTRYPOINT_BYTES

    if not was_line_truncated and not was_byte_truncated:
        return trimmed, line_count, byte_count, False, False

    truncated = '\n'.join(content_lines[:MAX_ENTRYPOINT_LINES]) if was_line_truncated else trimmed

    if len(truncated.encode('utf-8')) > MAX_ENTRYPOINT_BYTES:
        truncated_bytes = truncated.encode('utf-8')[:MAX_ENTRYPOINT_BYTES]
        try:
            truncated = truncated_bytes.decode('utf-8', errors='ignore')
            last_newline = truncated.rfind('\n')
            if last_newline > 0:
                truncated = truncated[:last_newline]
        except Exception:
            pass

    if was_byte_truncated and not was_line_truncated:
        reason = f"{byte_count} bytes (limit: {MAX_ENTRYPOINT_BYTES}) — index entries are too long"
    elif was_line_truncated and not was_byte_truncated:
        reason = f"{line_count} lines (limit: {MAX_ENTRYPOINT_LINES})"
    else:
        reason = f"{line_count} lines and {byte_count} bytes"

    warning = f"\n\n> WARNING: {ENTRYPOINT_NAME} is {reason}. Only part of it was loaded. Keep index entries to one line under ~200 chars; move detail into topic files."

    return truncated + warning, line_count, byte_count, was_line_truncated, was_byte_truncated


def ensure_memory_dir_exists(memory_dir: str):
    """Create ``memory_dir`` (and parents) when missing."""
    Path(memory_dir).mkdir(parents=True, exist_ok=True)


def load_memory_prompt(project_root: Optional[str] = None, skip_index: bool = False) -> Optional[str]:
    """
    Build the system-prompt block describing file-backed memories.

    Args:
        project_root: Optional override passed to ``get_auto_mem_path``.
        skip_index: Forwarded to ``build_memory_guidelines`` (simplified mode).

    Returns:
        Combined guideline + index text, or None when auto-memory is disabled.
    """
    if not is_auto_memory_enabled():
        return None

    memory_dir = get_auto_mem_path(project_root)
    ensure_memory_dir_exists(memory_dir)

    guidelines = build_memory_guidelines(memory_dir, skip_index)

    entrypoint_path = Path(memory_dir) / ENTRYPOINT_NAME
    entrypoint_content = ""

    if entrypoint_path.exists():
        try:
            with open(entrypoint_path, 'r', encoding='utf-8') as f:
                entrypoint_content = f.read()
        except Exception as e:
            print(f"Warning: Failed to read {ENTRYPOINT_NAME}: {e}")

    if entrypoint_content.strip():
        truncated, line_count, byte_count, was_line_truncated, was_byte_truncated = \
            truncate_entrypoint_content(entrypoint_content)

        guidelines.extend([
            "",
            "## Current Memory Index",
            "",
            truncated,
        ])

        if was_line_truncated or was_byte_truncated:
            print(f"Memory index truncated: {line_count} lines, {byte_count} bytes")

    return "\n".join(guidelines)


def format_memory_size(size_bytes: int) -> str:
    """Human-readable byte size (B / KB / MB)."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


if __name__ == "__main__":
    print("CktMem memdir smoke test")
    print("=" * 60)

    memory_dir = get_auto_mem_path()
    print(f"memory_dir={memory_dir}")

    ensure_memory_dir_exists(memory_dir)

    test_content = """# Memory Index

- [User Background](user_background.md) — EDA engineer focusing on ASAP7
- [Project Goals](project_goals.md) — Low-power RISC-V CPU design
- [Circuit Adder](circuit_adder.md) — 8-bit adder analysis
"""

    entrypoint_path = Path(memory_dir) / ENTRYPOINT_NAME
    with open(entrypoint_path, 'w', encoding='utf-8') as f:
        f.write(test_content)

    print(f"wrote test {ENTRYPOINT_NAME}")

    prompt = load_memory_prompt()
    if prompt:
        print(f"\nprompt_chars={len(prompt)}")
        print("\nfirst_500_chars:")
        print(prompt[:500])
    else:
        print("auto-memory disabled")

    print("\n" + "=" * 60)
