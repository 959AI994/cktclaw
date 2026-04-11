"""
Bootstrap State 测试

测试全局状态管理器的核心功能
"""

import asyncio
import pytest
from harness.bootstrap import (
    get_state_manager,
    get_session_id,
    get_cwd,
    set_cwd,
)


async def test_state_manager_singleton():
    """测试状态管理器单例模式"""
    manager1 = get_state_manager()
    manager2 = get_state_manager()
    assert manager1 is manager2, "StateManager 应该是单例"


async def test_session_id():
    """测试会话 ID"""
    session_id = await get_session_id()
    assert isinstance(session_id, str)
    assert len(session_id) == 16


async def test_cwd_operations():
    """测试工作目录操作"""
    manager = get_state_manager()

    # 获取初始 cwd
    initial_cwd = await get_cwd()
    assert isinstance(initial_cwd, str)

    # 设置新 cwd
    await set_cwd("/tmp")
    new_cwd = await get_cwd()
    assert "/tmp" in new_cwd


async def test_model_usage():
    """测试模型使用统计"""
    manager = get_state_manager()

    # 添加模型使用
    await manager.add_model_usage(
        "claude-3-5-sonnet-20241022",
        input_tokens=100,
        output_tokens=50,
    )

    # 获取统计
    stats = await manager.get_stats()
    assert "claude-3-5-sonnet-20241022" in stats["model_usage"]
    assert stats["model_usage"]["claude-3-5-sonnet-20241022"]["input_tokens"] == 100


async def test_cost_tracking():
    """测试成本跟踪"""
    manager = get_state_manager()

    # 添加成本
    await manager.add_cost(0.01)
    await manager.add_cost(0.02)

    # 获取统计
    stats = await manager.get_stats()
    assert stats["total_cost_usd"] >= 0.03


async def test_turn_counters():
    """测试轮次计数器"""
    manager = get_state_manager()

    # 重置计数器
    await manager.reset_turn_counters()

    # 增加计数
    await manager.increment_turn_tool_count()
    await manager.increment_turn_tool_count()
    await manager.increment_turn_hook_count()

    # 验证
    assert manager.state.turn_tool_count >= 2
    assert manager.state.turn_hook_count >= 1


async def test_lines_changed():
    """测试代码行数统计"""
    manager = get_state_manager()

    # 添加行数变更
    await manager.add_lines_changed(added=10, removed=5)

    # 获取统计
    stats = await manager.get_stats()
    assert stats["total_lines_added"] >= 10
    assert stats["total_lines_removed"] >= 5


def test_all():
    """运行所有测试"""
    print("="*70)
    print("Bootstrap State 测试")
    print("="*70)
    print()

    tests = [
        ("单例模式", test_state_manager_singleton),
        ("会话 ID", test_session_id),
        ("工作目录操作", test_cwd_operations),
        ("模型使用统计", test_model_usage),
        ("成本跟踪", test_cost_tracking),
        ("轮次计数器", test_turn_counters),
        ("代码行数统计", test_lines_changed),
    ]

    for name, test_func in tests:
        try:
            asyncio.run(test_func())
            print(f"✓ {name}")
        except Exception as e:
            print(f"✗ {name}: {e}")

    print()
    print("="*70)
    print("所有测试完成")
    print("="*70)


if __name__ == "__main__":
    test_all()
