"""
CktMem Memory Scan - 记忆文件扫描

参考 Claude Code 的 memoryScan.ts 实现
扫描记忆目录，读取 frontmatter，生成记忆清单
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from .paths import get_auto_mem_path, ENTRYPOINT_NAME


def parse_frontmatter(content: str) -> Optional[Dict[str, str]]:
    """
    解析 markdown frontmatter

    Args:
        content: 文件内容（前 30 行）

    Returns:
        frontmatter 字典，如果没有则返回 None
    """
    # 匹配 YAML frontmatter: ---\n...\n---
    pattern = r'^---\s*\n(.*?)\n---\s*\n'
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        return None

    frontmatter_text = match.group(1)
    frontmatter = {}

    # 简单解析 YAML（只支持 key: value 格式）
    for line in frontmatter_text.split('\n'):
        line = line.strip()
        if ':' in line:
            key, value = line.split(':', 1)
            frontmatter[key.strip()] = value.strip()

    return frontmatter


def scan_memory_files(memory_dir: Optional[str] = None, max_files: int = 200) -> List[Dict[str, Any]]:
    """
    扫描记忆目录中的所有 .md 文件

    Args:
        memory_dir: 记忆目录路径（可选，默认使用 get_auto_mem_path()）
        max_files: 最多扫描文件数

    Returns:
        记忆文件列表，每个包含：
        - path: 文件路径
        - name: 文件名
        - frontmatter: frontmatter 字典
        - mtime: 修改时间
        - size: 文件大小
    """
    if memory_dir is None:
        memory_dir = get_auto_mem_path()

    memory_path = Path(memory_dir)
    if not memory_path.exists():
        return []

    memories = []

    # 递归扫描所有 .md 文件
    for md_file in memory_path.rglob("*.md"):
        # 跳过 MEMORY.md
        if md_file.name == ENTRYPOINT_NAME:
            continue

        # 跳过隐藏文件
        if md_file.name.startswith('.'):
            continue

        try:
            # 读取前 30 行
            with open(md_file, 'r', encoding='utf-8') as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= 30:
                        break
                    lines.append(line)
                content = ''.join(lines)

            # 解析 frontmatter
            frontmatter = parse_frontmatter(content)

            # 获取文件信息
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

        # 限制文件数
        if len(memories) >= max_files:
            break

    # 按修改时间排序（新 → 旧）
    memories.sort(key=lambda m: m['mtime'], reverse=True)

    return memories


def format_memory_manifest(memories: List[Dict[str, Any]]) -> str:
    """
    格式化记忆清单（用于 LLM 选择相关记忆）

    Args:
        memories: 记忆文件列表

    Returns:
        格式化的清单文本
    """
    if not memories:
        return "No memories found."

    lines = ["# Available Memories", ""]

    for mem in memories:
        frontmatter = mem['frontmatter']
        name = frontmatter.get('name', mem['name'])
        description = frontmatter.get('description', '(no description)')
        mem_type = frontmatter.get('type', 'unknown')

        # 计算新鲜度
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
    # 测试记忆扫描
    print("CktMem Memory Scan 测试")
    print("=" * 60)

    memory_dir = get_auto_mem_path()
    print(f"扫描目录: {memory_dir}")

    # 创建测试记忆文件
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
        print(f"✓ 创建测试文件: {test_mem['filename']}")

    # 扫描记忆
    memories = scan_memory_files(memory_dir)
    print(f"\n找到 {len(memories)} 个记忆文件")

    # 格式化清单
    manifest = format_memory_manifest(memories)
    print("\n记忆清单:")
    print(manifest)

    print("\n" + "=" * 60)
