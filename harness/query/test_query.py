"""
Query 模块测试

测试查询循环的核心功能
"""

import asyncio
import sys
sys.path.insert(0, '/home/wjx/pythonproject/cktclaw')

from harness.query import (
    QueryState,
    QueryConfig,
    QueryResult,
    ContinueReason,
    TerminalReason,
    QueryLoop,
    create_query_loop,
    run_query,
)
from harness.query.query_types import (
    validate_tool_result_pairing,
    create_missing_tool_results,
)


async def test_query_state():
    """测试查询状态"""
    state = QueryState()
    assert state.turn_count == 1
    assert len(state.messages) == 0
    assert state.transition is None
    assert state.max_output_tokens_recovery_count == 0


async def test_query_config():
    """测试查询配置"""
    config = QueryConfig(
        system_prompt="Test prompt",
        max_turns=10,
        auto_compact_threshold=100_000,
    )
    assert config.system_prompt == "Test prompt"
    assert config.max_turns == 10
    assert config.auto_compact_threshold == 100_000
    assert config.auto_compact_enabled is True


async def test_validate_tool_result_pairing():
    """测试 Tool-Result 配对验证"""
    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "bash",
                    "input": {"command": "ls"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tool-1",
                    "content": "file1.txt",
                }
            ],
        },
    ]

    missing = validate_tool_result_pairing(messages)
    assert len(missing) == 0


async def test_validate_tool_result_pairing_missing():
    """测试缺失 Tool-Result"""
    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "bash",
                    "input": {"command": "ls"},
                },
                {
                    "type": "tool_use",
                    "id": "tool-2",
                    "name": "read",
                    "input": {"file": "test.txt"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tool-1",
                    "content": "file1.txt",
                }
            ],
        },
    ]

    missing = validate_tool_result_pairing(messages)
    assert len(missing) == 1
    assert "tool-2" in missing


async def test_create_missing_tool_results():
    """测试创建缺失的 Tool-Result"""
    missing_ids = ["tool-1", "tool-2"]
    results = create_missing_tool_results(missing_ids, "Interrupted")

    assert len(results) == 2
    assert results[0]["role"] == "user"
    assert results[0]["content"][0]["type"] == "tool_result"
    assert results[0]["content"][0]["tool_use_id"] == "tool-1"
    assert results[0]["content"][0]["is_error"] is True


async def test_query_loop_creation():
    """测试查询循环创建"""
    config = QueryConfig(system_prompt="Test")
    loop = create_query_loop(config)

    assert loop.config.system_prompt == "Test"
    assert loop.state.turn_count == 1
    assert loop.total_tokens == 0


async def test_query_loop_add_message():
    """测试添加消息"""
    config = QueryConfig(system_prompt="Test")
    loop = create_query_loop(config)

    message = {"role": "user", "content": "Hello"}
    loop.add_message(message)

    assert len(loop.state.messages) == 1
    assert loop.state.messages[0]["content"] == "Hello"


async def test_query_loop_update_usage():
    """测试更新使用统计"""
    config = QueryConfig(system_prompt="Test")
    loop = create_query_loop(config)

    loop.update_usage(1000, 0.01)
    assert loop.total_tokens == 1000
    assert loop.total_cost == 0.01

    loop.update_usage(500, 0.005)
    assert loop.total_tokens == 1500
    assert loop.total_cost == 0.015


async def test_query_loop_terminal_max_turns():
    """测试最大轮次终止"""
    config = QueryConfig(
        system_prompt="Test",
        max_turns=2,
    )
    loop = create_query_loop(config)

    # 第 1 轮
    loop.state.turn_count = 1
    terminal = loop._check_terminal_conditions()
    assert terminal is None

    # 第 3 轮（超过最大轮次）
    loop.state.turn_count = 3
    terminal = loop._check_terminal_conditions()
    assert terminal == TerminalReason.MAX_TURNS


async def test_query_loop_terminal_budget():
    """测试预算超限终止"""
    config = QueryConfig(
        system_prompt="Test",
        max_budget_usd=0.10,
    )
    loop = create_query_loop(config)

    # 未超限
    loop.total_cost = 0.05
    terminal = loop._check_terminal_conditions()
    assert terminal is None

    # 超限
    loop.total_cost = 0.15
    terminal = loop._check_terminal_conditions()
    assert terminal == TerminalReason.BUDGET_EXCEEDED


async def test_query_loop_estimate_tokens():
    """测试 Token 估算"""
    config = QueryConfig(system_prompt="Test")
    loop = create_query_loop(config)

    # 添加消息
    loop.add_message({"role": "user", "content": "Hello world"})
    loop.add_message({"role": "assistant", "content": "Hi there"})

    tokens = loop._estimate_tokens()
    assert tokens > 0


async def test_query_loop_should_auto_compact():
    """测试自动压缩判断"""
    config = QueryConfig(
        system_prompt="Test",
        auto_compact_threshold=100,
    )
    loop = create_query_loop(config)

    # 添加少量消息
    loop.add_message({"role": "user", "content": "Hi"})
    should_compact = loop._should_auto_compact()
    assert should_compact is False

    # 添加大量消息
    for i in range(100):
        loop.add_message({"role": "user", "content": "x" * 100})

    should_compact = loop._should_auto_compact()
    assert should_compact is True


async def test_query_loop_auto_compact():
    """测试自动压缩执行"""
    config = QueryConfig(system_prompt="Test")
    loop = create_query_loop(config)

    # 添加 20 条消息
    for i in range(20):
        loop.add_message({"role": "user", "content": f"Message {i}"})

    assert len(loop.state.messages) == 20

    # 执行压缩
    await loop._perform_auto_compact()

    # 应该只保留最近 5 条
    assert len(loop.state.messages) == 5


async def test_run_query_simple():
    """测试运行简单查询"""
    config = QueryConfig(
        system_prompt="Test",
        max_turns=1,
    )

    result = await run_query(config)

    assert result.terminal_reason == TerminalReason.END_TURN
    assert result.total_turns >= 1


async def test_query_loop_tool_result_healing():
    """测试 Tool-Result 自愈"""
    config = QueryConfig(system_prompt="Test", max_turns=1)
    loop = create_query_loop(config)

    # 添加缺失 tool_result 的消息
    loop.add_message({
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "tool-missing",
                "name": "bash",
                "input": {"command": "ls"},
            }
        ],
    })

    # 运行循环
    healed = False
    async for event in loop.run():
        if isinstance(event, dict) and event.get("type") == "tool_result_healing":
            healed = True
            assert "tool-missing" in event["missing_ids"]
            break

    assert healed


def test_all():
    """运行所有测试"""
    print("="*70)
    print("Query 模块测试")
    print("="*70)
    print()

    tests = [
        ("查询状态", test_query_state),
        ("查询配置", test_query_config),
        ("Tool-Result 配对验证", test_validate_tool_result_pairing),
        ("缺失 Tool-Result 检测", test_validate_tool_result_pairing_missing),
        ("创建缺失 Tool-Result", test_create_missing_tool_results),
        ("查询循环创建", test_query_loop_creation),
        ("添加消息", test_query_loop_add_message),
        ("更新使用统计", test_query_loop_update_usage),
        ("最大轮次终止", test_query_loop_terminal_max_turns),
        ("预算超限终止", test_query_loop_terminal_budget),
        ("Token 估算", test_query_loop_estimate_tokens),
        ("自动压缩判断", test_query_loop_should_auto_compact),
        ("自动压缩执行", test_query_loop_auto_compact),
        ("运行简单查询", test_run_query_simple),
        ("Tool-Result 自愈", test_query_loop_tool_result_healing),
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
