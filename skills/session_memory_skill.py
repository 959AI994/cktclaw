"""
Session Memory Skill - 会话记忆管理

允许 AI 自主保存和管理 Session Memory
"""

import sys
from pathlib import Path

# 确保可以导入 harness
_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import asyncio
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from cktclaw.harness import (
    SkillDefinition,
    SkillType,
    LoadedFrom,
    register_skill,
)


class SessionMemoryInput(BaseModel):
    """Session Memory input parameters."""
    topic: str = Field(..., description="Semantic topic (for example: circuit_adder, project_requirements)")
    summary: str = Field(..., description="One-line summary")
    content: str = Field(..., description="Full content")
    memory_type: str = Field(default="general", description="Memory type: general, circuit, requirement, decision")


async def session_memory_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Session Memory 技能执行器

    Args:
        args: 命令参数，格式：<topic>|<summary>|<content>|[memory_type]
        context: 执行上下文（包含 cli_state 等）

    Returns:
        工具结果消息列表
    """
    cli_state = context.get('cli_state')
    if not cli_state:
        return [{
            "type": "text",
            "text": "❌ Unable to get CLI state"
        }]

    # 解析输入
    parts = args.split('|')
    if len(parts) < 3:
        return [{
            "type": "text",
            "text": "❌ Invalid argument format. Expected: <topic>|<summary>|<content>|[memory_type]"
        }]

    topic = parts[0].strip()
    summary = parts[1].strip()
    content = parts[2].strip()
    memory_type = parts[3].strip() if len(parts) > 3 else "general"

    # 验证输入
    if not topic or not summary or not content:
        return [{
            "type": "text",
            "text": "❌ topic, summary, and content cannot be empty"
        }]

    try:
        # 保存到 Session Memory
        await cli_state.storage.save_session_memory(
            session_id=cli_state.session_id,
            topic=topic,
            summary=summary,
            content=content,
            memory_type=memory_type,
        )

        return [{
            "type": "text",
            "text": f"✅ Saved to Session Memory\n\nTopic: {topic}\nSummary: {summary}\nType: {memory_type}"
        }]

    except Exception as e:
        return [{
            "type": "text",
            "text": f"❌ Save failed: {str(e)}"
        }]


async def session_memory_list_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Read current session memory entries.

    Args:
        args: Optional max entries as integer string, default 10.
        context: Execution context.
    """
    cli_state = context.get("cli_state")
    if not cli_state:
        return [{"type": "text", "text": "❌ Unable to get CLI state"}]

    try:
        limit = int(args.strip()) if args and args.strip() else 10
    except ValueError:
        limit = 10

    limit = max(1, min(limit, 50))

    try:
        memories = await cli_state.storage.get_session_memories(cli_state.session_id)
        if not memories:
            return [{
                "type": "text",
                "text": "No saved session memory entries for this session."
            }]

        lines = [f"Session memory entries (showing up to {limit}):", ""]
        for idx, mem in enumerate(memories[:limit], start=1):
            lines.append(
                f"{idx}. topic={mem.get('topic', '')} | "
                f"type={mem.get('memory_type', 'general')} | "
                f"summary={mem.get('summary', '')}"
            )
        return [{"type": "text", "text": "\n".join(lines)}]
    except Exception as e:
        return [{"type": "text", "text": f"❌ Read failed: {e}"}]


# Define Session Memory Skill
SESSION_MEMORY_SKILL = SkillDefinition(
    name="save_session_memory",
    skill_type=SkillType.TOOL,
    description="Persist important information to Session Memory for the current session",
    display_name="Session Memory",
    aliases=["remember", "save_memory"],
    executor=session_memory_executor,
    loaded_from=LoadedFrom.BUNDLED,
    version="1.0.0",
    metadata={
        "author": "CktClaw Team",
        "category": "memory",
        "tags": ["memory", "session", "persistence"],
    }
)

SESSION_MEMORY_LIST_SKILL = SkillDefinition(
    name="list_session_memory",
    skill_type=SkillType.TOOL,
    description="List saved session memory entries for current session",
    display_name="Session Memory List",
    aliases=["show_memory", "memory_list", "recall_memory"],
    executor=session_memory_list_executor,
    argument_hint="[max_entries]",
    argument_names=["max_entries"],
    loaded_from=LoadedFrom.BUNDLED,
    version="1.0.0",
    metadata={
        "author": "CktClaw Team",
        "category": "memory",
        "tags": ["memory", "session", "read"],
    }
)


async def register():
    """Register Session Memory skills."""
    await register_skill(SESSION_MEMORY_SKILL)
    await register_skill(SESSION_MEMORY_LIST_SKILL)
    return [SESSION_MEMORY_SKILL, SESSION_MEMORY_LIST_SKILL]


if __name__ == "__main__":
    # 测试 Skill 注册
    async def test():
        skill = await register()
        print(f"✓ Session Memory Skill registered: {skill.name}")
        print(f"  Display Name: {skill.display_name}")
        print(f"  Description: {skill.description}")
        print(f"  Aliases: {skill.aliases}")

    asyncio.run(test())
