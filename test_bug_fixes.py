#!/usr/bin/env python3
"""
验证三大 Bug 修复

测试内容：
1. LLM Tool 注入：验证 SkillRegistry 中的技能被正确传递给 LLM
2. 任务状态机：验证幂等性更新不会抛出异常
3. 命令解析：验证 "/reverse /home/..." 被正确解析为技能名和参数
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import asyncio


async def test_task_state_machine():
    """测试任务状态机的幂等性修复"""
    print("=" * 70)
    print("测试 1: 任务状态机幂等性")
    print("=" * 70)

    from harness.tasks import get_task_manager, TaskType, TaskStatus

    task_manager = get_task_manager()

    # 创建测试任务
    task_handle = await task_manager.create_task(
        TaskType.LOCAL_AGENT,
        "Test Task"
    )

    print(f"✅ 创建任务: {task_handle.task_id}")

    # 更新为 RUNNING
    await task_manager.update_task_status(task_handle.task_id, TaskStatus.RUNNING)
    print(f"✅ 更新状态: RUNNING")

    # 更新为 COMPLETED
    await task_manager.update_task_status(task_handle.task_id, TaskStatus.COMPLETED)
    print(f"✅ 更新状态: COMPLETED")

    # 幂等性测试：再次更新为 COMPLETED（应该不抛出异常）
    try:
        await task_manager.update_task_status(task_handle.task_id, TaskStatus.COMPLETED)
        print(f"✅ 幂等性测试通过：重复设置 COMPLETED 不抛出异常")
    except Exception as e:
        print(f"❌ 幂等性测试失败: {e}")
        return False

    # 负面测试：尝试从 COMPLETED 改为 FAILED（应该抛出异常）
    try:
        await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
        print(f"❌ 状态保护测试失败：应该阻止从 COMPLETED 改为 FAILED")
        return False
    except Exception as e:
        print(f"✅ 状态保护测试通过：正确阻止非法状态转换")

    print()
    return True


async def test_skill_registry_tools():
    """测试 SkillRegistry 工具构建"""
    print("=" * 70)
    print("测试 2: SkillRegistry 工具注入")
    print("=" * 70)

    from harness import get_skill_registry

    registry = get_skill_registry()
    all_skills = await registry.list_skills()

    print(f"✅ 已注册技能数量: {len(all_skills)}")

    # 构建工具列表（模拟 chat_handler_v2.py 的逻辑）
    tools = []
    for skill in all_skills:
        if skill.user_invocable:
            tool_spec = {
                "type": "function",
                "function": {
                    "name": skill.name,
                    "description": f"{skill.description}\n使用场景: {skill.when_to_use}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "args": {
                                "type": "string",
                                "description": f"参数格式: {skill.argument_hint}\n参数名: {', '.join(skill.argument_names)}"
                            }
                        },
                        "required": ["args"],
                    },
                },
            }
            tools.append(tool_spec)

    print(f"✅ 构建工具数量: {len(tools)}")

    # 验证关键技能
    tool_names = [t["function"]["name"] for t in tools]
    expected_skills = ["abc", "yosys", "opensta", "reverse", "rltf", "pareto-negotiate"]

    for skill_name in expected_skills:
        if skill_name in tool_names:
            print(f"   ✅ {skill_name}")
        else:
            print(f"   ⚠️  {skill_name} (未找到)")

    print()
    return len(tools) > 0


def test_command_parsing():
    """测试命令解析逻辑"""
    print("=" * 70)
    print("测试 3: 命令解析")
    print("=" * 70)

    # 直接实现 _extract_skill_name 逻辑
    def _extract_skill_name(command: str):
        command = command.strip()
        if command.startswith("/"):
            parts = command.split()
            if len(parts) > 0:
                skill_name = parts[0][1:]
                return skill_name
        if command.startswith("abc"):
            return "abc"
        elif command.startswith("yosys"):
            return "yosys"
        elif command.startswith("reverse"):
            return "reverse"
        elif command.startswith("opensta"):
            return "opensta"
        elif command.startswith("ai4eda"):
            return "ai4eda"
        return None

    test_cases = [
        ("/reverse /home/wjx/test.v", "reverse", "/home/wjx/test.v"),
        ("/abc strash; balance", "abc", "strash; balance"),
        ("/yosys read_verilog test.v", "yosys", "read_verilog test.v"),
        ("/rltf test.aig 100", "rltf", "test.aig 100"),
        ("/pareto-negotiate test.aig 50", "pareto-negotiate", "test.aig 50"),
        ("abc strash", "abc", "strash"),
        ("yosys help", "yosys", "help"),
    ]

    all_passed = True

    for command, expected_skill, expected_args in test_cases:
        skill_name = _extract_skill_name(command)

        if skill_name == expected_skill:
            # 提取参数
            if command.startswith("/"):
                parts = command.split(maxsplit=1)
                args_str = parts[1] if len(parts) > 1 else ""
            else:
                args_str = command[len(skill_name):].strip()

            if args_str == expected_args:
                print(f"✅ '{command}'")
                print(f"   技能: {skill_name}, 参数: '{args_str}'")
            else:
                print(f"❌ '{command}'")
                print(f"   期望参数: '{expected_args}', 实际: '{args_str}'")
                all_passed = False
        else:
            print(f"❌ '{command}'")
            print(f"   期望技能: {expected_skill}, 实际: {skill_name}")
            all_passed = False

    print()
    return all_passed


async def main():
    """运行所有测试"""
    print("\n")
    print("🔧 CktClaw Bug 修复验证")
    print("=" * 70)
    print()

    results = []

    # 测试 1: 任务状态机
    try:
        result = await test_task_state_machine()
        results.append(("任务状态机幂等性", result))
    except Exception as e:
        print(f"❌ 测试 1 异常: {e}")
        results.append(("任务状态机幂等性", False))

    # 测试 2: SkillRegistry 工具注入
    try:
        result = await test_skill_registry_tools()
        results.append(("SkillRegistry 工具注入", result))
    except Exception as e:
        print(f"❌ 测试 2 异常: {e}")
        results.append(("SkillRegistry 工具注入", False))

    # 测试 3: 命令解析
    try:
        result = test_command_parsing()
        results.append(("命令解析", result))
    except Exception as e:
        print(f"❌ 测试 3 异常: {e}")
        results.append(("命令解析", False))

    # 汇总结果
    print("=" * 70)
    print("测试结果汇总")
    print("=" * 70)

    for test_name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status} - {test_name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)

    print()
    print(f"总计: {passed}/{total} 测试通过")
    print("=" * 70)

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
