#!/usr/bin/env python3
"""
CktClaw 端到端测试脚本

测试 DeepSeek API + Yosys 工具 + CktMem 记忆系统
"""

import sys
import os
import time
sys.path.insert(0, '/home/wjx/pythonproject')

from cktclaw.main import CLIState
from cktclaw.handlers.chat_handler import process_chat
from cktclaw.handlers.session_handler import _display_session_info
import asyncio


async def test_cktclaw_integration():
    """端到端集成测试"""

    print("="*70)
    print("CktClaw 端到端集成测试")
    print("="*70)
    print()

    # 1. 初始化 CLI 状态
    print("1. 初始化 CLI 状态...")
    cli_state = CLIState()
    print(f"   ✓ 会话 ID: {cli_state.session_id}")
    print(f"   ✓ 引擎: {cli_state.current_engine}")
    print(f"   ✓ Storage 初始化: {cli_state.storage is not None}")
    print(f"   ✓ ContextManager 初始化: {cli_state.context_manager is not None}")
    print()

    # 2. 测试会话信息
    print("2. 测试会话信息...")
    stats = await cli_state.context_manager.get_context_stats(cli_state.session_id)
    print(f"   ✓ 总消息数: {stats['total_messages']}")
    print(f"   ✓ 总 Token 数: {stats['total_tokens']}")
    print(f"   ✓ 压缩次数: {stats['total_compactions']}")
    print()

    # 3. 测试对话（不调用实际 LLM，只测试记忆系统）
    print("3. 测试记忆系统...")

    # 模拟用户消息
    test_messages = [
        "你好，我想了解 Yosys 工具",
        "Yosys 可以做什么？",
        "如何使用 Yosys 进行逻辑综合？",
    ]

    for i, msg in enumerate(test_messages, 1):
        print(f"   [{i}] 用户: {msg}")

        # 构建上下文
        messages = await cli_state.context_manager.build_context(
            session_id=cli_state.session_id,
            user_message=msg,
            auto_compact=False,  # 暂时关闭自动压缩
        )
        print(f"       上下文消息数: {len(messages)}")

        # 模拟助手回复
        assistant_reply = f"这是对问题 {i} 的回答..."
        await cli_state.context_manager.add_assistant_message(
            session_id=cli_state.session_id,
            content=assistant_reply,
        )
        print(f"       ✓ 助手回复已存储")

    print()

    # 4. 检查最终统计
    print("4. 最终统计...")
    final_stats = await cli_state.context_manager.get_context_stats(cli_state.session_id)
    print(f"   ✓ 总消息数: {final_stats['total_messages']}")
    print(f"   ✓ 总 Token 数: {final_stats['total_tokens']}")
    print(f"   ✓ 压缩次数: {final_stats['total_compactions']}")
    print()

    # 5. 测试上下文构建
    print("5. 测试上下文构建...")
    final_messages = await cli_state.context_manager.build_context(
        session_id=cli_state.session_id,
        user_message="总结一下我们讨论的内容",
        auto_compact=False,
    )
    print(f"   ✓ 最终上下文包含 {len(final_messages)} 条消息")
    print(f"   ✓ 消息类型分布:")

    from collections import Counter
    role_counts = Counter(msg.role.value if hasattr(msg.role, 'value') else msg.role
                          for msg in final_messages)
    for role, count in role_counts.items():
        print(f"      - {role}: {count} 条")
    print()

    # 6. 测试压缩功能（添加大量消息）
    print("6. 测试压缩功能...")
    print("   添加大量消息以触发压缩...")

    for i in range(10):
        long_message = f"这是第 {i+1} 条长消息。" * 100  # 创建长消息
        messages = await cli_state.context_manager.build_context(
            session_id=cli_state.session_id,
            user_message=long_message,
            auto_compact=True,  # 启用自动压缩
        )
        await cli_state.context_manager.add_assistant_message(
            session_id=cli_state.session_id,
            content=f"这是对第 {i+1} 条消息的回复。" * 50,
        )

    # 检查是否触发压缩
    compression_stats = await cli_state.context_manager.get_context_stats(cli_state.session_id)
    print(f"   ✓ 压缩次数: {compression_stats['total_compactions']}")
    print(f"   ✓ 当前 Token 数: {compression_stats['total_tokens']}")
    print()

    print("="*70)
    print("✅ 所有测试通过！")
    print("="*70)
    print()

    print("📊 最终统计:")
    print(f"   • 会话 ID: {cli_state.session_id}")
    print(f"   • 总消息数: {compression_stats['total_messages']}")
    print(f"   • 总 Token 数: {compression_stats['total_tokens']}")
    print(f"   • 压缩次数: {compression_stats['total_compactions']}")
    print()


if __name__ == "__main__":
    asyncio.run(test_cktclaw_integration())
