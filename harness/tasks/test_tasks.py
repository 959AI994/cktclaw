"""
Tasks 模块测试

测试任务生命周期管理的核心功能
"""

import asyncio
import os
import sys
sys.path.insert(0, '/home/wjx/pythonproject/cktclaw')

from harness.tasks import (
    TaskType,
    TaskStatus,
    TaskManager,
    get_task_manager,
    generate_task_id,
    is_terminal_task_status,
)


async def test_task_manager_singleton():
    """测试任务管理器单例模式"""
    manager1 = get_task_manager()
    manager2 = get_task_manager()
    assert manager1 is manager2, "TaskManager 应该是单例"


async def test_generate_task_id():
    """测试任务 ID 生成"""
    task_id = generate_task_id(TaskType.LOCAL_BASH)
    assert isinstance(task_id, str)
    assert len(task_id) == 9  # 1 prefix + 8 random chars
    assert task_id.startswith("b")

    agent_id = generate_task_id(TaskType.LOCAL_AGENT)
    assert agent_id.startswith("a")


async def test_terminal_status():
    """测试终止状态判断"""
    assert is_terminal_task_status(TaskStatus.COMPLETED)
    assert is_terminal_task_status(TaskStatus.FAILED)
    assert is_terminal_task_status(TaskStatus.KILLED)
    assert not is_terminal_task_status(TaskStatus.PENDING)
    assert not is_terminal_task_status(TaskStatus.RUNNING)


async def test_create_task():
    """测试创建任务"""
    manager = get_task_manager()
    manager.reset()

    handle = await manager.create_task(
        task_type=TaskType.LOCAL_BASH,
        description="Test bash command",
        tool_use_id="test_tool_001",
    )

    assert isinstance(handle.task_id, str)
    assert len(handle.task_id) == 9

    # 验证任务状态
    task = await manager.get_task(handle.task_id)
    assert task.type == TaskType.LOCAL_BASH
    assert task.status == TaskStatus.PENDING
    assert task.description == "Test bash command"
    assert task.tool_use_id == "test_tool_001"


async def test_task_lifecycle():
    """测试任务生命周期"""
    manager = get_task_manager()
    manager.reset()

    # 创建任务
    handle = await manager.create_task(
        task_type=TaskType.LOCAL_AGENT,
        description="Test agent task",
    )

    # 更新为 running
    await manager.update_task_status(handle.task_id, TaskStatus.RUNNING)
    task = await manager.get_task(handle.task_id)
    assert task.status == TaskStatus.RUNNING

    # 更新为 completed
    await manager.update_task_status(handle.task_id, TaskStatus.COMPLETED)
    task = await manager.get_task(handle.task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.end_time is not None


async def test_task_output():
    """测试任务输出"""
    manager = get_task_manager()
    manager.reset()

    # 创建任务
    handle = await manager.create_task(
        task_type=TaskType.LOCAL_BASH,
        description="Test output",
    )

    # 追加输出
    await manager.append_task_output(handle.task_id, "Line 1\n")
    await manager.append_task_output(handle.task_id, "Line 2\n")

    # 读取输出
    output = await manager.read_task_output(handle.task_id)
    assert "Line 1" in output
    assert "Line 2" in output


async def test_list_tasks():
    """测试任务列表"""
    manager = get_task_manager()
    manager.reset()

    # 创建多个任务
    handle1 = await manager.create_task(TaskType.LOCAL_BASH, "Task 1")
    handle2 = await manager.create_task(TaskType.LOCAL_AGENT, "Task 2")
    handle3 = await manager.create_task(TaskType.LOCAL_BASH, "Task 3")

    # 更新状态
    await manager.update_task_status(handle1.task_id, TaskStatus.RUNNING)
    await manager.update_task_status(handle2.task_id, TaskStatus.COMPLETED)

    # 列出所有任务
    all_tasks = await manager.list_tasks()
    assert len(all_tasks) == 3

    # 按状态过滤
    running_tasks = await manager.list_tasks(status=TaskStatus.RUNNING)
    assert len(running_tasks) == 1

    # 按类型过滤
    bash_tasks = await manager.list_tasks(task_type=TaskType.LOCAL_BASH)
    assert len(bash_tasks) == 2


async def test_background_tasks():
    """测试后台任务"""
    manager = get_task_manager()
    manager.reset()

    # 创建任务
    handle1 = await manager.create_task(TaskType.LOCAL_BASH, "Task 1")
    handle2 = await manager.create_task(TaskType.LOCAL_AGENT, "Task 2")
    handle3 = await manager.create_task(TaskType.LOCAL_BASH, "Task 3")
    handle4 = await manager.create_task(TaskType.LOCAL_BASH, "Task 4")

    # 更新状态
    await manager.update_task_status(handle1.task_id, TaskStatus.RUNNING)
    await manager.update_task_status(handle2.task_id, TaskStatus.RUNNING)
    await manager.update_task_status(handle3.task_id, TaskStatus.COMPLETED)
    # handle4 保持 pending

    # 获取后台任务
    bg_tasks = await manager.get_background_tasks()
    assert len(bg_tasks) == 3  # 2 running + 1 pending


async def test_kill_task():
    """测试终止任务"""
    manager = get_task_manager()
    manager.reset()

    # 创建任务
    handle = await manager.create_task(TaskType.LOCAL_BASH, "Test kill")
    await manager.update_task_status(handle.task_id, TaskStatus.RUNNING)

    # 注册清理函数
    cleanup_called = False
    def cleanup():
        nonlocal cleanup_called
        cleanup_called = True

    await manager.register_cleanup_handler(handle.task_id, cleanup)

    # 终止任务
    await manager.kill_task(handle.task_id)

    # 验证
    task = await manager.get_task(handle.task_id)
    assert task.status == TaskStatus.KILLED
    assert task.end_time is not None
    assert cleanup_called


async def test_task_stats():
    """测试任务统计"""
    manager = get_task_manager()
    manager.reset()

    # 创建任务
    await manager.create_task(TaskType.LOCAL_BASH, "Task 1")
    await manager.create_task(TaskType.LOCAL_BASH, "Task 2")
    await manager.create_task(TaskType.LOCAL_AGENT, "Task 3")

    # 获取统计
    stats = await manager.get_stats()
    assert stats["total_tasks"] == 3
    assert stats["by_status"]["pending"] == 3
    assert stats["by_type"]["local_bash"] == 2
    assert stats["by_type"]["local_agent"] == 1


async def test_cleanup_terminal_tasks():
    """测试清理终止任务"""
    manager = get_task_manager()
    manager.reset()

    # 创建任务
    handle1 = await manager.create_task(TaskType.LOCAL_BASH, "Task 1")
    handle2 = await manager.create_task(TaskType.LOCAL_BASH, "Task 2")

    # 完成任务
    await manager.update_task_status(handle1.task_id, TaskStatus.COMPLETED)
    await manager.update_task_status(handle2.task_id, TaskStatus.FAILED)

    # 清理（max_age_seconds=0 立即清理）
    cleaned = await manager.cleanup_terminal_tasks(max_age_seconds=0)
    assert cleaned == 2

    # 验证
    all_tasks = await manager.list_tasks()
    assert len(all_tasks) == 0


def test_all():
    """运行所有测试"""
    print("="*70)
    print("Tasks 模块测试")
    print("="*70)
    print()

    tests = [
        ("单例模式", test_task_manager_singleton),
        ("任务 ID 生成", test_generate_task_id),
        ("终止状态判断", test_terminal_status),
        ("创建任务", test_create_task),
        ("任务生命周期", test_task_lifecycle),
        ("任务输出", test_task_output),
        ("任务列表", test_list_tasks),
        ("后台任务", test_background_tasks),
        ("终止任务", test_kill_task),
        ("任务统计", test_task_stats),
        ("清理终止任务", test_cleanup_terminal_tasks),
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
