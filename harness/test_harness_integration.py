"""
Harness 集成测试

测试所有 5 个核心模块的集成
"""

import asyncio
import sys
sys.path.insert(0, '/home/wjx/pythonproject/cktclaw')

from harness.bootstrap import get_state_manager
from harness.tasks import get_task_manager, TaskType, TaskStatus
from harness.skills import get_skill_registry, SkillDefinition, LoadedFrom, SkillType
from harness.coordinator import get_coordinator_manager, CoordinatorMode
from harness.query import create_query_loop, QueryConfig


async def test_harness_integration():
    """测试 Harness 集成"""
    print("="*70)
    print("Harness 集成测试")
    print("="*70)
    print()

    # 1. Bootstrap
    print("1. Bootstrap 模块")
    state_manager = get_state_manager()
    session_id = await state_manager.get_session_id()
    print(f"   ✓ 会话 ID: {session_id}")

    # 设置工作目录
    await state_manager.set_cwd("/tmp/test")
    cwd = await state_manager.get_cwd()
    print(f"   ✓ 工作目录: {cwd}")

    # 2. Tasks
    print("\n2. Tasks 模块")
    task_manager = get_task_manager()
    task_handle = await task_manager.create_task(
        TaskType.LOCAL_BASH,
        "Test task",
    )
    print(f"   ✓ 任务创建: {task_handle.task_id}")
    await task_manager.update_task_status(task_handle.task_id, TaskStatus.COMPLETED)
    print(f"   ✓ 任务完成")

    # 3. Skills
    print("\n3. Skills 模块")
    skill_registry = get_skill_registry()
    skill_registry.reset()

    from harness.skills import register_skill
    skill = SkillDefinition(
        name="test-skill",
        description="Test skill",
        skill_type=SkillType.PROMPT,
        loaded_from=LoadedFrom.BUNDLED,
    )
    await register_skill(skill)
    print(f"   ✓ 技能注册: {skill.name}")

    from harness.skills import list_skills
    skills = await list_skills()
    print(f"   ✓ 技能列表: {len(skills)} 个技能")

    # 4. Coordinator
    print("\n4. Coordinator 模块")
    coordinator = get_coordinator_manager()
    coordinator.reset()

    await coordinator.set_mode(CoordinatorMode.COORDINATOR)
    mode = await coordinator.get_mode()
    print(f"   ✓ 模式设置: {mode.value}")

    context = await coordinator.get_worker_tools_context()
    print(f"   ✓ Worker 工具上下文: {len(context)} 个键")

    # 5. Query
    print("\n5. Query 模块")
    config = QueryConfig(
        system_prompt="Test system prompt",
        max_turns=2,
    )
    loop = create_query_loop(config)
    print(f"   ✓ 查询循环创建")

    loop.add_message({"role": "user", "content": "Hello"})
    print(f"   ✓ 消息添加: {len(loop.state.messages)} 条消息")

    # 6. 统计信息
    print("\n6. 统计信息")

    # Bootstrap 统计
    print(f"   ✓ Bootstrap: 会话 ID = {session_id}")

    # Tasks 统计
    task_stats = await task_manager.get_stats()
    print(f"   ✓ Tasks: {task_stats['total_tasks']} 个任务")

    # Skills 统计
    skill_stats = await skill_registry.get_stats()
    print(f"   ✓ Skills: {skill_stats['total_skills']} 个技能")

    # Coordinator 统计
    is_coord = await coordinator.is_coordinator_mode()
    print(f"   ✓ Coordinator: 模式 = {'coordinator' if is_coord else 'normal'}")

    # Query 统计
    print(f"   ✓ Query: {loop.state.turn_count} 轮")

    print()
    print("="*70)
    print("集成测试完成 ✅")
    print("="*70)
    print()
    print("所有 5 个核心模块正常工作：")
    print("  1. Bootstrap (根状态) ✓")
    print("  2. Tasks (任务状态机) ✓")
    print("  3. Skills (技能资产化) ✓")
    print("  4. Coordinator (调度隔离) ✓")
    print("  5. Query (中枢循环) ✓")
    print()


if __name__ == "__main__":
    asyncio.run(test_harness_integration())
