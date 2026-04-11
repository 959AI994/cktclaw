"""
Coordinator 模块测试

测试调度管理器的核心功能
"""

import asyncio
import sys
sys.path.insert(0, '/home/wjx/pythonproject/cktclaw')

from harness.coordinator import (
    CoordinatorMode,
    CoordinatorManager,
    get_coordinator_manager,
    is_coordinator_mode,
    get_worker_tools_context,
    get_coordinator_system_prompt,
    WorkerNotification,
    NotificationStatus,
    WorkerUsage,
)
from harness.coordinator.coordinator_types import (
    parse_worker_notification,
    format_worker_notification,
)


async def test_coordinator_manager_singleton():
    """测试 Coordinator 管理器单例模式"""
    manager1 = get_coordinator_manager()
    manager2 = get_coordinator_manager()
    assert manager1 is manager2, "CoordinatorManager 应该是单例"


async def test_mode_management():
    """测试模式管理"""
    manager = get_coordinator_manager()
    manager.reset()

    # 默认模式
    mode = await manager.get_mode()
    assert mode == CoordinatorMode.NORMAL

    # 切换到 Coordinator 模式
    await manager.set_mode(CoordinatorMode.COORDINATOR)
    mode = await manager.get_mode()
    assert mode == CoordinatorMode.COORDINATOR

    # 检查 is_coordinator_mode
    is_coord = await manager.is_coordinator_mode()
    assert is_coord is True

    # 切换回 Normal 模式
    await manager.set_mode(CoordinatorMode.NORMAL)
    is_coord = await manager.is_coordinator_mode()
    assert is_coord is False


async def test_match_session_mode():
    """测试会话模式匹配"""
    manager = get_coordinator_manager()
    manager.reset()

    # 当前是 Normal，会话是 Coordinator
    warning = await manager.match_session_mode("coordinator")
    assert warning is not None
    assert "Entered coordinator mode" in warning

    # 验证模式已切换
    mode = await manager.get_mode()
    assert mode == CoordinatorMode.COORDINATOR

    # 再次匹配，应该没有警告
    warning = await manager.match_session_mode("coordinator")
    assert warning is None

    # 切换回 Normal
    warning = await manager.match_session_mode("normal")
    assert warning is not None
    assert "Exited coordinator mode" in warning


async def test_worker_tools_context():
    """测试 Worker 工具上下文"""
    manager = get_coordinator_manager()
    manager.reset()

    # Normal 模式下应该返回空字典
    context = await manager.get_worker_tools_context()
    assert context == {}

    # Coordinator 模式下应该返回工具列表
    await manager.set_mode(CoordinatorMode.COORDINATOR)
    context = await manager.get_worker_tools_context()
    assert "workerToolsContext" in context
    assert "Bash" in context["workerToolsContext"]
    assert "Read" in context["workerToolsContext"]
    assert "Edit" in context["workerToolsContext"]


async def test_worker_tools_context_with_mcp():
    """测试带 MCP 服务器的 Worker 工具上下文"""
    manager = get_coordinator_manager()
    manager.reset()

    await manager.configure(
        mode=CoordinatorMode.COORDINATOR,
        mcp_servers=["server1", "server2"],
    )

    context = await manager.get_worker_tools_context()
    assert "MCP tools" in context["workerToolsContext"]
    assert "server1" in context["workerToolsContext"]
    assert "server2" in context["workerToolsContext"]


async def test_worker_tools_context_with_scratchpad():
    """测试带 Scratchpad 的 Worker 工具上下文"""
    manager = get_coordinator_manager()
    manager.reset()

    await manager.configure(
        mode=CoordinatorMode.COORDINATOR,
        scratchpad_dir="/tmp/scratchpad",
    )

    context = await manager.get_worker_tools_context()
    assert "Scratchpad directory" in context["workerToolsContext"]
    assert "/tmp/scratchpad" in context["workerToolsContext"]


async def test_coordinator_system_prompt():
    """测试 Coordinator 系统 Prompt"""
    manager = get_coordinator_manager()
    manager.reset()

    # Normal 模式下应该返回空字符串
    prompt = await manager.get_coordinator_system_prompt()
    assert prompt == ""

    # Coordinator 模式下应该返回完整 Prompt
    await manager.set_mode(CoordinatorMode.COORDINATOR)
    prompt = await manager.get_coordinator_system_prompt()
    assert len(prompt) > 0
    assert "coordinator" in prompt.lower()
    assert "Agent" in prompt
    assert "SendMessage" in prompt
    assert "TaskStop" in prompt


async def test_parse_worker_notification():
    """测试解析 Worker 通知"""
    xml = """<task-notification>
<task-id>agent-a1b</task-id>
<status>completed</status>
<summary>Agent completed successfully</summary>
<result>Found the bug in validate.ts:42</result>
<usage>
  <total_tokens>1000</total_tokens>
  <tool_uses>5</tool_uses>
  <duration_ms>3000</duration_ms>
</usage>
</task-notification>"""

    notification = parse_worker_notification(xml)
    assert notification is not None
    assert notification.task_id == "agent-a1b"
    assert notification.status == NotificationStatus.COMPLETED
    assert notification.summary == "Agent completed successfully"
    assert notification.result == "Found the bug in validate.ts:42"
    assert notification.usage is not None
    assert notification.usage.total_tokens == 1000
    assert notification.usage.tool_uses == 5
    assert notification.usage.duration_ms == 3000


async def test_parse_worker_notification_minimal():
    """测试解析最小 Worker 通知"""
    xml = """<task-notification>
<task-id>agent-xyz</task-id>
<status>failed</status>
<summary>Agent failed</summary>
</task-notification>"""

    notification = parse_worker_notification(xml)
    assert notification is not None
    assert notification.task_id == "agent-xyz"
    assert notification.status == NotificationStatus.FAILED
    assert notification.summary == "Agent failed"
    assert notification.result is None
    assert notification.usage is None


async def test_format_worker_notification():
    """测试格式化 Worker 通知"""
    notification = WorkerNotification(
        task_id="agent-test",
        status=NotificationStatus.COMPLETED,
        summary="Test completed",
        result="Test result",
        usage=WorkerUsage(
            total_tokens=500,
            tool_uses=3,
            duration_ms=2000,
        ),
    )

    xml = format_worker_notification(notification)
    assert "<task-id>agent-test</task-id>" in xml
    assert "<status>completed</status>" in xml
    assert "<summary>Test completed</summary>" in xml
    assert "<result>Test result</result>" in xml
    assert "<total_tokens>500</total_tokens>" in xml


async def test_parse_notification_via_manager():
    """测试通过 Manager 解析通知"""
    manager = get_coordinator_manager()

    xml = """<task-notification>
<task-id>agent-123</task-id>
<status>completed</status>
<summary>Done</summary>
</task-notification>"""

    notification = await manager.parse_notification(xml)
    assert notification is not None
    assert notification.task_id == "agent-123"


async def test_configure():
    """测试配置 Coordinator"""
    manager = get_coordinator_manager()
    manager.reset()

    await manager.configure(
        mode=CoordinatorMode.COORDINATOR,
        worker_tools=["Bash", "Read", "Edit", "Grep"],
        mcp_servers=["test-server"],
        scratchpad_dir="/tmp/test",
    )

    # 验证配置
    mode = await manager.get_mode()
    assert mode == CoordinatorMode.COORDINATOR

    context = await manager.get_worker_tools_context()
    assert "Grep" in context["workerToolsContext"]
    assert "test-server" in context["workerToolsContext"]
    assert "/tmp/test" in context["workerToolsContext"]


async def test_convenience_functions():
    """测试便捷函数"""
    manager = get_coordinator_manager()
    manager.reset()

    # is_coordinator_mode
    await manager.set_mode(CoordinatorMode.COORDINATOR)
    is_coord = await is_coordinator_mode()
    assert is_coord is True

    # get_worker_tools_context
    context = await get_worker_tools_context()
    assert "workerToolsContext" in context

    # get_coordinator_system_prompt
    prompt = await get_coordinator_system_prompt()
    assert len(prompt) > 0


def test_all():
    """运行所有测试"""
    print("="*70)
    print("Coordinator 模块测试")
    print("="*70)
    print()

    tests = [
        ("单例模式", test_coordinator_manager_singleton),
        ("模式管理", test_mode_management),
        ("会话模式匹配", test_match_session_mode),
        ("Worker 工具上下文", test_worker_tools_context),
        ("Worker 工具上下文（MCP）", test_worker_tools_context_with_mcp),
        ("Worker 工具上下文（Scratchpad）", test_worker_tools_context_with_scratchpad),
        ("Coordinator 系统 Prompt", test_coordinator_system_prompt),
        ("解析 Worker 通知", test_parse_worker_notification),
        ("解析最小 Worker 通知", test_parse_worker_notification_minimal),
        ("格式化 Worker 通知", test_format_worker_notification),
        ("通过 Manager 解析通知", test_parse_notification_via_manager),
        ("配置 Coordinator", test_configure),
        ("便捷函数", test_convenience_functions),
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
