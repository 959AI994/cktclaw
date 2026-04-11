"""
Session Memory Skill - 会话记忆管理

允许 AI 自主保存和管理 Session Memory
"""

import sys
from pathlib import Path

# 确保可以导入 harness
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import asyncio
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from harness import (
    SkillDefinition,
    SkillType,
    LoadedFrom,
    register_skill,
)


class SessionMemoryInput(BaseModel):
    """Session Memory 输入参数"""
    topic: str = Field(..., description="语义主题（如 circuit_adder, project_requirements）")
    summary: str = Field(..., description="一行摘要")
    content: str = Field(..., description="完整内容")
    memory_type: str = Field(default="general", description="记忆类型：general, circuit, requirement, decision")


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
            "text": "❌ 无法获取 CLI 状态"
        }]

    # 解析输入
    parts = args.split('|')
    if len(parts) < 3:
        return [{
            "type": "text",
            "text": "❌ 参数格式错误。格式：<topic>|<summary>|<content>|[memory_type]"
        }]

    topic = parts[0].strip()
    summary = parts[1].strip()
    content = parts[2].strip()
    memory_type = parts[3].strip() if len(parts) > 3 else "general"

    # 验证输入
    if not topic or not summary or not content:
        return [{
            "type": "text",
            "text": "❌ topic, summary, content 不能为空"
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
            "text": f"✅ 已保存到 Session Memory\n\n主题: {topic}\n摘要: {summary}\n类型: {memory_type}"
        }]

    except Exception as e:
        return [{
            "type": "text",
            "text": f"❌ 保存失败: {str(e)}"
        }]


# 定义 Session Memory Skill
SESSION_MEMORY_SKILL = SkillDefinition(
    name="save_session_memory",
    skill_type=SkillType.TOOL,
    description="保存重要信息到 Session Memory，用于在当前会话中持久化记忆",
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


async def register():
    """注册 Session Memory Skill"""
    await register_skill(SESSION_MEMORY_SKILL)
    return SESSION_MEMORY_SKILL


if __name__ == "__main__":
    # 测试 Skill 注册
    async def test():
        skill = await register()
        print(f"✓ Session Memory Skill registered: {skill.name}")
        print(f"  Display Name: {skill.display_name}")
        print(f"  Description: {skill.description}")
        print(f"  Aliases: {skill.aliases}")

    asyncio.run(test())
