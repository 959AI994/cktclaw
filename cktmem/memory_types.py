"""
CktMem Memory Types - 记忆类型定义

参考 Claude Code 的 memoryTypes.ts 实现
定义记忆的类型、frontmatter 格式、使用指南
"""

from typing import List

# 记忆类型定义
MEMORY_TYPES = {
    "user": {
        "name": "User Preferences & Context",
        "description": "用户的个人偏好、工作方式、背景信息",
        "examples": [
            "用户是 EDA 工程师，专注于 ASAP7 工艺",
            "用户喜欢简洁的代码风格",
            "用户的项目目标是优化面积和功耗",
        ]
    },
    "feedback": {
        "name": "Feedback & Corrections",
        "description": "用户的反馈、纠正、不喜欢的行为",
        "examples": [
            "用户不喜欢过于冗长的解释",
            "用户希望优先使用 Yosys 而不是 ABC",
            "用户纠正：这个电路是乘法器，不是加法器",
        ]
    },
    "project": {
        "name": "Project Context",
        "description": "项目级的上下文、需求、设计决策",
        "examples": [
            "项目目标：设计一个低功耗的 RISC-V CPU",
            "设计约束：时钟频率 2GHz，面积 < 0.5mm²",
            "已完成的电路：adder, multiplier, alu",
        ]
    },
    "reference": {
        "name": "Reference Information",
        "description": "参考信息、工具用法、常用命令",
        "examples": [
            "Yosys 综合命令：synth -top module_name",
            "ASAP7 标准单元库路径",
            "常用的优化策略",
        ]
    },
}

# Frontmatter 示例
MEMORY_FRONTMATTER_EXAMPLE = [
    "```markdown",
    "---",
    "name: User's EDA Background",
    "description: User is an EDA engineer focusing on ASAP7 process",
    "type: user",
    "---",
    "",
    "The user is an experienced EDA engineer...",
    "```",
]

# 类型说明章节
TYPES_SECTION = [
    "## Memory Types",
    "",
    "Organize memories into these types:",
    "",
]

for mem_type, info in MEMORY_TYPES.items():
    TYPES_SECTION.extend([
        f"**{info['name']}** (`type: {mem_type}`)",
        f"- {info['description']}",
        f"- Examples: {', '.join(info['examples'][:2])}",
        "",
    ])

# 不应该保存的内容
WHAT_NOT_TO_SAVE_SECTION = [
    "## What NOT to save",
    "",
    "Do not save information that can be easily derived from:",
    "- Reading the code or circuit files",
    "- Running standard EDA tools",
    "- Checking file timestamps or git history",
    "",
    "Memory is for context that would otherwise be lost between conversations.",
]

# 何时访问记忆
WHEN_TO_ACCESS_SECTION = [
    "## When to access memories",
    "",
    "- At the start of a conversation to understand user context",
    "- When user asks about past work or decisions",
    "- When you need project-specific information",
    "- Before making design decisions that might conflict with user preferences",
]

# 信任召回
TRUSTING_RECALL_SECTION = [
    "## Trusting recall",
    "",
    "Memories may become outdated. When in doubt:",
    "- Check current code/files to verify",
    "- Ask the user if something seems inconsistent",
    "- Update or remove outdated memories",
]


def build_memory_guidelines(memory_dir: str, skip_index: bool = False) -> List[str]:
    """
    构建记忆使用指南

    Args:
        memory_dir: 记忆目录路径
        skip_index: 是否跳过索引步骤（简化模式）

    Returns:
        指南文本行列表
    """
    how_to_save = []

    if skip_index:
        how_to_save = [
            "## How to save memories",
            "",
            "Write each memory to its own file (e.g., `user_eda_background.md`, `project_requirements.md`) using this frontmatter format:",
            "",
            *MEMORY_FRONTMATTER_EXAMPLE,
            "",
            "- Keep the name, description, and type fields up-to-date",
            "- Organize memory semantically by topic, not chronologically",
            "- Update or remove memories that turn out to be wrong or outdated",
            "- Do not write duplicate memories. Check existing memories first.",
        ]
    else:
        how_to_save = [
            "## How to save memories",
            "",
            "Saving a memory is a two-step process:",
            "",
            "**Step 1** — write the memory to its own file (e.g., `user_eda_background.md`) using this frontmatter format:",
            "",
            *MEMORY_FRONTMATTER_EXAMPLE,
            "",
            f"**Step 2** — add a pointer to that file in `MEMORY.md`. `MEMORY.md` is an index, not a memory — each entry should be one line, under ~150 characters: `- [Title](file.md) — one-line hook`. It has no frontmatter. Never write memory content directly into `MEMORY.md`.",
            "",
            f"- `MEMORY.md` is always loaded into your conversation context — lines after {MAX_ENTRYPOINT_LINES} will be truncated, so keep the index concise",
            "- Keep the name, description, and type fields in memory files up-to-date",
            "- Organize memory semantically by topic, not chronologically",
            "- Update or remove memories that turn out to be wrong or outdated",
            "- Do not write duplicate memories. Check existing memories first.",
        ]

    lines = [
        "# Session Memory",
        "",
        f"You have a persistent, file-based memory system at `{memory_dir}`. This directory already exists.",
        "",
        "You should build up this memory system over time so that future conversations can have a complete picture of the project context, user preferences, design decisions, and important circuit information.",
        "",
        "If the user explicitly asks you to remember something, save it immediately as whichever type fits best. If they ask you to forget something, find and remove the relevant entry.",
        "",
        *TYPES_SECTION,
        *WHAT_NOT_TO_SAVE_SECTION,
        "",
        *how_to_save,
        "",
        *WHEN_TO_ACCESS_SECTION,
        "",
        *TRUSTING_RECALL_SECTION,
        "",
        "## Memory and other forms of persistence",
        "Memory is for information that should persist across conversations. For information only relevant to the current conversation, use regular chat context instead.",
        "",
    ]

    return lines


# 导入常量供外部使用
from .paths import MAX_ENTRYPOINT_LINES

if __name__ == "__main__":
    # 测试指南生成
    guidelines = build_memory_guidelines("/home/user/.cktclaw/projects/test/memory")
    print("\n".join(guidelines))
