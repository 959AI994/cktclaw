"""
CktMem memory types — taxonomy, frontmatter samples, and guideline assembly.

Defines the ``type`` field values surfaced in memory markdown plus helper
sections stitched into the system prompt.
"""

from typing import List

MEMORY_TYPES = {
    "user": {
        "name": "User Preferences & Context",
        "description": "Personal preferences, working style, and background.",
        "examples": [
            "User is an EDA engineer focused on the ASAP7 PDK.",
            "User prefers concise explanations and small diffs.",
            "Project goals emphasize area and power trade-offs.",
        ]
    },
    "feedback": {
        "name": "Feedback & Corrections",
        "description": "Corrections, dislikes, or clarifications about assistant behavior.",
        "examples": [
            "User dislikes overly verbose tool narration.",
            "User prefers Yosys over ABC for this repo.",
            "Correction: the highlighted block is a multiplier, not an adder.",
        ]
    },
    "project": {
        "name": "Project Context",
        "description": "Project-level requirements, constraints, and design decisions.",
        "examples": [
            "Goal: low-power RISC-V CPU prototype.",
            "Constraint: 2 GHz target, die area < 0.5 mm².",
            "Completed macros: adder, multiplier, ALU.",
        ]
    },
    "reference": {
        "name": "Reference Information",
        "description": "Commands, tool paths, and reusable cheat-sheets.",
        "examples": [
            "Yosys one-liner: synth -top <module>.",
            "ASAP7 standard-cell library install path.",
            "Common optimization recipes for this flow.",
        ]
    },
}

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

WHEN_TO_ACCESS_SECTION = [
    "## When to access memories",
    "",
    "- At the start of a conversation to understand user context",
    "- When user asks about past work or decisions",
    "- When you need project-specific information",
    "- Before making design decisions that might conflict with user preferences",
]

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
    Build the markdown lines describing how to use the memory directory.

    Args:
        memory_dir: Absolute memory root shown to the model.
        skip_index: When True, omit the two-step MEMORY.md index instructions.

    Returns:
        Lines ready to join into a system-prompt section.
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


from .paths import MAX_ENTRYPOINT_LINES

if __name__ == "__main__":
    guidelines = build_memory_guidelines("/home/user/.cktclaw/projects/test/memory")
    print("\n".join(guidelines))
