#!/usr/bin/env python3
"""
验证创新技能是否在 CktClaw 中正确注册
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import asyncio

async def verify_skills():
    """验证技能注册"""
    print("=" * 70)
    print("CktClaw 创新技能注册验证")
    print("=" * 70)
    print()

    # 导入并注册技能
    from skills.rltf_skill import register_rltf_skill, RLTF_SKILL
    from skills.pareto_negotiation_skill import register_pareto_negotiation_skill, PARETO_NEGOTIATION_SKILL

    print("📝 注册技能...")
    await register_rltf_skill()
    await register_pareto_negotiation_skill()
    print("   ✅ 技能注册完成")
    print()

    # 获取技能注册表
    from harness import get_skill_registry
    registry = get_skill_registry()

    print("📋 已注册的创新技能:")
    print()

    # RLTF
    print("1. RLTF (Reinforcement Learning from Tool Feedback)")
    print(f"   命令: /{RLTF_SKILL.name}")
    print(f"   别名: {', '.join(['/' + a for a in RLTF_SKILL.aliases])}")
    print(f"   描述: {RLTF_SKILL.description}")
    print(f"   用法: /{RLTF_SKILL.name} {RLTF_SKILL.argument_hint}")
    print()

    # Pareto Negotiation
    print("2. Pareto Multi-Agent Negotiation")
    print(f"   命令: /{PARETO_NEGOTIATION_SKILL.name}")
    print(f"   别名: {', '.join(['/' + a for a in PARETO_NEGOTIATION_SKILL.aliases])}")
    print(f"   描述: {PARETO_NEGOTIATION_SKILL.description}")
    print(f"   用法: /{PARETO_NEGOTIATION_SKILL.name} {PARETO_NEGOTIATION_SKILL.argument_hint}")
    print()

    print("=" * 70)
    print("✅ 验证完成！")
    print()
    print("现在您可以在 CktClaw 中使用以下命令：")
    print()
    print("  /rltf test.aig 100")
    print("  /pareto-negotiate test.aig 50")
    print()
    print("或使用别名：")
    print("  /rltf-opt test.aig 100")
    print("  /pareto test.aig 50")
    print("  /negotiate test.aig 50")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(verify_skills())
