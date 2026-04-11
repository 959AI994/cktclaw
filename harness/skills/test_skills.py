"""
Skills 模块测试

测试技能注册与管理的核心功能
"""

import asyncio
import os
import sys
sys.path.insert(0, '/home/wjx/pythonproject/cktclaw')

from harness.skills import (
    SkillType,
    SkillDefinition,
    LoadedFrom,
    SkillRegistry,
    get_skill_registry,
    register_skill,
    get_skill,
    list_skills,
)


async def test_skill_registry_singleton():
    """测试技能注册表单例模式"""
    registry1 = get_skill_registry()
    registry2 = get_skill_registry()
    assert registry1 is registry2, "SkillRegistry 应该是单例"


async def test_register_skill():
    """测试注册技能"""
    registry = get_skill_registry()
    registry.reset()

    skill = SkillDefinition(
        name="test-skill",
        description="A test skill",
        when_to_use="Use this for testing",
        loaded_from=LoadedFrom.BUNDLED,
    )

    await register_skill(skill)

    # 验证注册成功
    retrieved = await get_skill("test-skill")
    assert retrieved.name == "test-skill"
    assert retrieved.description == "A test skill"


async def test_skill_aliases():
    """测试技能别名"""
    registry = get_skill_registry()
    registry.reset()

    skill = SkillDefinition(
        name="commit",
        description="Create a git commit",
        aliases=["ci", "c"],
        loaded_from=LoadedFrom.BUNDLED,
    )

    await register_skill(skill)

    # 通过别名获取
    skill1 = await get_skill("commit")
    skill2 = await get_skill("ci")
    skill3 = await get_skill("c")

    assert skill1.name == "commit"
    assert skill2.name == "commit"
    assert skill3.name == "commit"


async def test_list_skills():
    """测试列出技能"""
    registry = get_skill_registry()
    registry.reset()

    # 注册多个技能
    await register_skill(SkillDefinition(
        name="skill1",
        description="Skill 1",
        skill_type=SkillType.PROMPT,
        loaded_from=LoadedFrom.BUNDLED,
    ))
    await register_skill(SkillDefinition(
        name="skill2",
        description="Skill 2",
        skill_type=SkillType.TOOL,
        loaded_from=LoadedFrom.USER_SETTINGS,
    ))
    await register_skill(SkillDefinition(
        name="skill3",
        description="Skill 3",
        skill_type=SkillType.PROMPT,
        loaded_from=LoadedFrom.BUNDLED,
        user_invocable=False,
    ))

    # 列出所有技能
    all_skills = await list_skills()
    assert len(all_skills) == 3

    # 按类型过滤
    prompt_skills = await list_skills(skill_type=SkillType.PROMPT)
    assert len(prompt_skills) == 2

    # 按来源过滤
    bundled_skills = await list_skills(loaded_from=LoadedFrom.BUNDLED)
    assert len(bundled_skills) == 2

    # 仅用户可调用
    user_invocable = await list_skills(user_invocable_only=True)
    assert len(user_invocable) == 2


async def test_unregister_skill():
    """测试注销技能"""
    registry = get_skill_registry()
    registry.reset()

    skill = SkillDefinition(
        name="temp-skill",
        description="Temporary skill",
        aliases=["tmp"],
        loaded_from=LoadedFrom.BUNDLED,
    )

    await register_skill(skill)
    assert len(await list_skills()) == 1

    # 注销技能
    await registry.unregister_skill("temp-skill")
    assert len(await list_skills()) == 0

    # 别名也应该被删除
    try:
        await get_skill("tmp")
        assert False, "别名应该被删除"
    except Exception:
        pass


async def test_conditional_skills():
    """测试条件技能"""
    registry = get_skill_registry()
    registry.reset()

    # 注册条件技能（有路径过滤）
    skill = SkillDefinition(
        name="python-helper",
        description="Python helper skill",
        paths=["*.py", "**/*.py"],
        loaded_from=LoadedFrom.PROJECT_SETTINGS,
    )

    await register_skill(skill)

    # 条件技能不应该立即可用
    all_skills = await list_skills()
    assert len(all_skills) == 0

    # 检查条件技能数量
    conditional_count = await registry.get_conditional_skill_count()
    assert conditional_count == 1

    # 激活条件技能
    activated = await registry.activate_conditional_skills_for_paths(
        ["test.py", "src/main.py"],
        os.getcwd(),
    )

    assert len(activated) == 1
    assert "python-helper" in activated

    # 现在应该可用
    all_skills = await list_skills()
    assert len(all_skills) == 1


async def test_skill_execution():
    """测试技能执行"""
    registry = get_skill_registry()
    registry.reset()

    # 定义执行函数
    async def custom_executor(args: str, context: dict):
        return [{"type": "text", "text": f"Executed with args: {args}"}]

    skill = SkillDefinition(
        name="custom-skill",
        description="Custom skill with executor",
        executor=custom_executor,
        loaded_from=LoadedFrom.BUNDLED,
    )

    await register_skill(skill)

    # 执行技能
    retrieved = await get_skill("custom-skill")
    result = await retrieved.get_prompt_for_command("test-arg")

    assert len(result) == 1
    assert "test-arg" in result[0]["text"]


async def test_skill_stats():
    """测试技能统计"""
    registry = get_skill_registry()
    registry.reset()

    # 注册多个技能
    await register_skill(SkillDefinition(
        name="skill1",
        description="Skill 1",
        skill_type=SkillType.PROMPT,
        loaded_from=LoadedFrom.BUNDLED,
    ))
    await register_skill(SkillDefinition(
        name="skill2",
        description="Skill 2",
        skill_type=SkillType.PROMPT,
        loaded_from=LoadedFrom.USER_SETTINGS,
        aliases=["s2"],
    ))

    # 获取统计
    stats = await registry.get_stats()
    assert stats["total_skills"] == 2
    assert stats["total_aliases"] == 1
    assert stats["by_type"]["prompt"] == 2
    assert stats["by_source"]["bundled"] == 1
    assert stats["by_source"]["userSettings"] == 1


async def test_user_facing_name():
    """测试用户可见名称"""
    skill1 = SkillDefinition(
        name="internal-name",
        description="Test",
        loaded_from=LoadedFrom.BUNDLED,
    )
    assert skill1.user_facing_name() == "internal-name"

    skill2 = SkillDefinition(
        name="internal-name",
        display_name="User Friendly Name",
        description="Test",
        loaded_from=LoadedFrom.BUNDLED,
    )
    assert skill2.user_facing_name() == "User Friendly Name"


async def test_skill_override():
    """测试技能覆盖"""
    registry = get_skill_registry()
    registry.reset()

    skill1 = SkillDefinition(
        name="test",
        description="Version 1",
        loaded_from=LoadedFrom.BUNDLED,
    )
    await register_skill(skill1)

    # 不允许覆盖
    skill2 = SkillDefinition(
        name="test",
        description="Version 2",
        loaded_from=LoadedFrom.USER_SETTINGS,
    )
    try:
        await register_skill(skill2, override=False)
        assert False, "应该抛出异常"
    except ValueError:
        pass

    # 允许覆盖
    await register_skill(skill2, override=True)
    retrieved = await get_skill("test")
    assert retrieved.description == "Version 2"


def test_all():
    """运行所有测试"""
    print("="*70)
    print("Skills 模块测试")
    print("="*70)
    print()

    tests = [
        ("单例模式", test_skill_registry_singleton),
        ("注册技能", test_register_skill),
        ("技能别名", test_skill_aliases),
        ("列出技能", test_list_skills),
        ("注销技能", test_unregister_skill),
        ("条件技能", test_conditional_skills),
        ("技能执行", test_skill_execution),
        ("技能统计", test_skill_stats),
        ("用户可见名称", test_user_facing_name),
        ("技能覆盖", test_skill_override),
    ]

    for name, test_func in tests:
        try:
            asyncio.run(test_func())
            print(f"✓ {name}")
        except Exception as e:
            print(f"✗ {name}: {e}")
            import traceback
            traceback.print_exc()

    print()
    print("="*70)
    print("所有测试完成")
    print("="*70)


if __name__ == "__main__":
    test_all()
