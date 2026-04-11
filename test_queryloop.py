#!/usr/bin/env python3
"""
QueryLoop 端到端测试

测试 QueryLoop 的完整工作流程：
1. LLM 调用
2. 工具调用检测
3. 工具执行
4. 多轮循环
"""

import asyncio
import json
from typing import List, Dict, Any

from harness.query import QueryLoop, QueryConfig, QueryStateEnum, create_query_loop


# Mock LLM 函数
async def mock_llm_func(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """模拟 LLM 调用"""
    print(f"[LLM] Received {len(messages)} messages")

    # 检查最后一条消息
    last_msg = messages[-1] if messages else {}

    # 如果是工具结果，返回最终响应
    if last_msg.get("role") == "tool":
        return {
            "role": "assistant",
            "content": f"工具执行完成，结果是: {last_msg.get('content', 'N/A')}"
        }

    # 否则，返回工具调用
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_test_1",
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "arguments": json.dumps({"arg": "value"})
                }
            }
        ]
    }


# Mock 工具执行函数
async def mock_tool_executor(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """模拟工具执行"""
    print(f"[TOOL] Executing {tool_name} with args: {tool_args}")
    await asyncio.sleep(0.1)  # 模拟执行时间
    return f"Tool {tool_name} executed successfully with {tool_args}"


async def test_queryloop():
    """测试 QueryLoop"""
    print("=" * 60)
    print("QueryLoop 端到端测试")
    print("=" * 60)

    # 创建配置
    config = QueryConfig(
        system_prompt="You are a helpful assistant.",
        max_turns=3,
        auto_compact_enabled=False,  # 禁用压缩以简化测试
    )

    # 创建 QueryLoop
    loop = create_query_loop(
        llm_func=mock_llm_func,
        tool_executor=mock_tool_executor,
        config=config,
    )

    # 初始消息
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "请执行一个测试工具"}
    ]

    print("\n[TEST] Starting QueryLoop...")
    print(f"[TEST] Initial messages: {len(messages)}")

    # 运行 QueryLoop
    result = None
    turn = 0
    async for partial_result in loop.run(messages):
        turn += 1
        print(f"\n--- Turn {turn} ---")
        print(f"State: {partial_result.state.value}")

        if partial_result.state == QueryStateEnum.LLM_CALLING:
            print("  → Calling LLM...")

        elif partial_result.state == QueryStateEnum.TOOL_EXECUTING:
            print(f"  → Executing tool: {partial_result.current_tool_name}")

        elif partial_result.state == QueryStateEnum.CONTINUING:
            print("  → Continuing to next turn...")

        elif partial_result.state == QueryStateEnum.TERMINAL:
            print(f"  → Terminal reason: {partial_result.terminal_reason.value}")
            print(f"  → Final response: {partial_result.final_response}")
            result = partial_result

    # 验证结果
    print("\n" + "=" * 60)
    print("测试结果")
    print("=" * 60)

    if result:
        print(f"✓ QueryLoop 完成")
        print(f"  - 总轮次: {result.total_turns}")
        print(f"  - 工具调用次数: {result.tool_calls}")
        print(f"  - 终止原因: {result.terminal_reason.value}")
        print(f"  - 最终响应: {result.final_response}")
        print(f"  - 消息数: {len(result.messages)}")

        # 验证预期
        assert result.total_turns >= 1, "应该至少有 1 轮"
        assert result.tool_calls >= 1, "应该至少调用 1 次工具"
        assert result.terminal_reason.value == "end_turn", "应该正常结束"
        assert result.final_response, "应该有最终响应"

        print("\n✓ 所有断言通过")
        return True
    else:
        print("✗ QueryLoop 未返回结果")
        return False


async def test_no_tool_call():
    """测试无工具调用的情况"""
    print("\n" + "=" * 60)
    print("测试：无工具调用")
    print("=" * 60)

    async def simple_llm(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "role": "assistant",
            "content": "这是一个简单的响应，不需要工具调用。"
        }

    config = QueryConfig(
        system_prompt="You are a helpful assistant.",
        max_turns=1,
    )

    loop = create_query_loop(
        llm_func=simple_llm,
        tool_executor=mock_tool_executor,
        config=config,
    )

    messages = [
        {"role": "user", "content": "Hello"}
    ]

    result = None
    async for partial_result in loop.run(messages):
        if partial_result.state == QueryStateEnum.TERMINAL:
            result = partial_result

    assert result is not None, "应该返回结果"
    assert result.tool_calls == 0, "不应该有工具调用"
    assert result.final_response == "这是一个简单的响应，不需要工具调用。"

    print("✓ 无工具调用测试通过")
    return True


async def test_max_turns():
    """测试最大轮次限制"""
    print("\n" + "=" * 60)
    print("测试：最大轮次限制")
    print("=" * 60)

    async def infinite_tool_llm(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        # 总是返回工具调用，模拟无限循环
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": f"call_{len(messages)}",
                    "type": "function",
                    "function": {
                        "name": "test_tool",
                        "arguments": "{}"
                    }
                }
            ]
        }

    config = QueryConfig(
        system_prompt="Test",
        max_turns=2,  # 限制最大轮次
    )

    loop = create_query_loop(
        llm_func=infinite_tool_llm,
        tool_executor=mock_tool_executor,
        config=config,
    )

    messages = [{"role": "user", "content": "Test"}]

    result = None
    async for partial_result in loop.run(messages):
        if partial_result.state == QueryStateEnum.TERMINAL:
            result = partial_result

    assert result is not None, "应该返回结果"
    assert result.terminal_reason.value == "max_turns", "应该因为达到最大轮次而终止"
    assert result.total_turns > config.max_turns, "轮次应该超过限制"

    print("✓ 最大轮次限制测试通过")
    return True


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("QueryLoop 测试套件")
    print("=" * 60)

    tests = [
        ("基本工作流程", test_queryloop),
        ("无工具调用", test_no_tool_call),
        ("最大轮次限制", test_max_turns),
    ]

    results = []
    for name, test_func in tests:
        try:
            success = await test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n✗ 测试失败: {name}")
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    for name, success in results:
        status = "✓" if success else "✗"
        print(f"{status} {name}")

    passed = sum(1 for _, success in results if success)
    total = len(results)
    print(f"\n通过: {passed}/{total}")

    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print("\n❌ 部分测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
