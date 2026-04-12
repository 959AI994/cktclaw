"""
CktMem memory scan — walk markdown files and extract lightweight metadata.

Reads only the first lines for frontmatter parsing, skips the index file, and
produces a manifest suitable for LLM-based retrieval.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from .paths import get_auto_mem_path, ENTRYPOINT_NAME


def parse_frontmatter(content: str) -> Optional[Dict[str, str]]:
    """
    Parse a leading ``---`` YAML block when present.

    Args:
        content: Typically the first ~30 lines of a markdown file.

    Returns:
        Key/value map or None when no frontmatter delimiter is found.
    """
    pattern = r'^---\s*\n(.*?)\n---\s*\n'
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        return None

    frontmatter_text = match.group(1)
    frontmatter = {}

    for line in frontmatter_text.split('\n'):
        line = line.strip()
        if ':' in line:
            key, value = line.split(':', 1)
            frontmatter[key.strip()] = value.strip()

    return frontmatter


def scan_memory_files(memory_dir: Optional[str] = None, max_files: int = 200) -> List[Dict[str, Any]]:
    """
    Recursively collect ``*.md`` files under the memory root.

    Args:
        memory_dir: Optional override; defaults to ``get_auto_mem_path()``.
        max_files: Stop after this many successfully parsed files.

    Returns:
        Dict rows with path, name, relative_path, frontmatter, mtime, size.
    """
    if memory_dir is None:
        memory_dir = get_auto_mem_path()

    memory_path = Path(memory_dir)
    if not memory_path.exists():
        return []

    memories = []

    for md_file in memory_path.rglob("*.md"):
        if md_file.name == ENTRYPOINT_NAME:
            continue

        if md_file.name.startswith('.'):
            continue

        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= 30:
                        break
                    lines.append(line)
                content = ''.join(lines)

            frontmatter = parse_frontmatter(content)

            stat = md_file.stat()

            memories.append({
                'path': str(md_file),
                'name': md_file.name,
                'relative_path': str(md_file.relative_to(memory_path)),
                'frontmatter': frontmatter or {},
                'mtime': datetime.fromtimestamp(stat.st_mtime),
                'size': stat.st_size,
            })

        except Exception as e:
            print(f"Warning: Failed to scan {md_file}: {e}")
            continue

        if len(memories) >= max_files:
            break

    memories.sort(key=lambda m: m['mtime'], reverse=True)

    return memories


def format_memory_manifest(memories: List[Dict[str, Any]]) -> str:
    """
    Render ``memories`` into a compact bullet list for the selection prompt.
    """
    if not memories:
        return "No memories found."

    lines = ["# Available Memories", ""]

    for mem in memories:
        frontmatter = mem['frontmatter']
        name = frontmatter.get('name', mem['name'])
        description = frontmatter.get('description', '(no description)')
        mem_type = frontmatter.get('type', 'unknown')

        days_ago = (datetime.now() - mem['mtime']).days
        freshness = ""
        if days_ago == 0:
            freshness = "today"
        elif days_ago == 1:
            freshness = "yesterday"
        elif days_ago < 7:
            freshness = f"{days_ago} days ago"
        elif days_ago < 30:
            freshness = f"{days_ago // 7} weeks ago"
        else:
            freshness = f"{days_ago // 30} months ago"

        lines.append(f"- **{name}** (`{mem['relative_path']}`) — {description}")
        lines.append(f"  Type: {mem_type} | Updated: {freshness}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print("CktMem memory_scan smoke test")
    print("=" * 60)

    memory_dir = get_auto_mem_path()
    print(f"scan_dir={memory_dir}")

    test_memories = [
        {
            'filename': 'user_background.md',
            'content': """---
name: User's EDA Background
description: User is an EDA engineer focusing on ASAP7 process
type: user
---

The user is an experienced EDA engineer specializing in ASAP7 process technology.
They prefer Yosys for synthesis and focus on area/power optimization.
"""
        },
        {
            'filename': 'project_goals.md',
            'content': """---
name: Project Goals
description: Low-power RISC-V CPU design
type: project
---

Project: Design a low-power RISC-V CPU core
Target: Clock frequency 2GHz, area < 0.5mm²
Process: ASAP7 (7nm)
"""
        },
    ]

    memory_path = Path(memory_dir)
    for test_mem in test_memories:
        file_path = memory_path / test_mem['filename']
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(test_mem['content'])
        print(f"wrote test file {test_mem['filename']}")

    memories = scan_memory_files(memory_dir)
    print(f"\nfiles_found={len(memories)}")

    manifest = format_memory_manifest(memories)
    print("\nmanifest:")
    print(manifest)

    print("\n" + "=" * 60)
