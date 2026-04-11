#!/usr/bin/env python3
"""
CktMem 压缩功能测试

测试自动压缩功能，生成大量消息触发压缩
"""

import sys
import asyncio
sys.path.insert(0, '/home/wjx/pythonproject')

from cktclaw.main import CLIState


async def test_compression():
    """测试压缩功能"""

    print("="*70)
    print("CktMem 压缩功能测试")
    print("="*70)
    print()

    # 1. 初始化
    print("1. 初始化 CktClaw 状态...")
    cli_state = CLIState()
    session_id = cli_state.session_id
    print(f"   ✓ 会话 ID: {session_id}")
    print(f"   ✓ 压缩阈值: 150,000 tokens")
    print()

    # 2. 生成大量消息
    print("2. 生成大量消息以触发压缩...")
    print("   策略: 每条消息 ~1000 tokens，需要 ~150 条消息")
    print()

    # 创建长消息模板
    long_text = """
    This is a detailed discussion about digital circuit design and EDA tools.
    We are exploring various aspects of logic synthesis, optimization, and verification.
    The conversation covers topics like Yosys, ABC, OpenSTA, and other important tools.
    We discuss implementation strategies, best practices, and common pitfalls.
    """ * 50  # 重复 50 次，约 1000 tokens

    rounds = 80  # 生成 80 轮对话，约 160,000 tokens

    for i in range(rounds):
        if i % 10 == 0:
            print(f"   进度: {i}/{rounds} 轮...")

        user_msg = f"Round {i+1}: {long_text}"
        assistant_msg = f"Response to round {i+1}: {long_text}"

        # 构建上下文（启用自动压缩）
        messages = await cli_state.context_manager.build_context(
            session_id=session_id,
            user_message=user_msg,
            auto_compact=True,  # 启用自动压缩
        )

        # 存储助手回复
        await cli_state.context_manager.add_assistant_message(
            session_id=session_id,
            content=assistant_msg,
        )

        # 每 10 轮检查一次统计
        if (i + 1) % 10 == 0:
            stats = await cli_state.context_manager.get_context_stats(session_id)
            print(f"       Token 数: {stats['total_tokens']:,}, 压缩次数: {stats['total_compactions']}")

    print()

    # 3. 最终统计
    print("3. 最终统计...")
    final_stats = await cli_state.context_manager.get_context_stats(session_id)
    print(f"   ✓ 总消息数: {final_stats['total_messages']}")
    print(f"   ✓ 总 Token 数: {final_stats['total_tokens']:,}")
    print(f"   ✓ 压缩次数: {final_stats['total_compactions']}")
    print()

    # 4. 检查压缩历史
    print("4. 检查压缩历史...")
    conn = cli_state.storage._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT compact_type, pre_compact_tokens, post_compact_tokens,
               tokens_saved, created_at
        FROM compact_history
        WHERE session_id = ?
        ORDER BY created_at
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()

    if rows:
        print(f"   ✓ 找到 {len(rows)} 次压缩记录:")
        for i, row in enumerate(rows, 1):
            compact_type, pre, post, saved, created_at = row
            ratio = (saved / pre * 100) if pre > 0 else 0
            print(f"      [{i}] 类型: {compact_type}")
            print(f"          压缩前: {pre:,} tokens")
            print(f"          压缩后: {post:,} tokens")
            print(f"          节省: {saved:,} tokens ({ratio:.1f}%)")
            print(f"          时间: {created_at}")
            print()
    else:
        print("   ⚠ 未触发压缩（可能 Token 数未达阈值）")
        print()

    # 5. 验证上下文完整性
    print("5. 验证上下文完整性...")
    test_messages = await cli_state.context_manager.build_context(
        session_id=session_id,
        user_message="Test message after compression",
        auto_compact=False,
    )
    print(f"   ✓ 上下文消息数: {len(test_messages)}")

    # 检查消息类型分布
    from collections import Counter
    msg_types = Counter(
        msg.msg_type.value if hasattr(msg.msg_type, 'value') else msg.msg_type
        for msg in test_messages
    )
    print(f"   ✓ 消息类型分布:")
    for msg_type, count in msg_types.items():
        print(f"      - {msg_type}: {count} 条")

    # 检查是否有 compact_boundary
    has_boundary = any(
        (msg.msg_type.value if hasattr(msg.msg_type, 'value') else msg.msg_type) == 'compact_boundary'
        for msg in test_messages
    )
    print(f"   ✓ 包含压缩边界: {'是' if has_boundary else '否'}")
    print()

    print("="*70)
    print("✅ 压缩功能测试完成！")
    print("="*70)
    print()

    print("📊 测试总结:")
    print(f"   • 生成对话轮数: {rounds}")
    print(f"   • 最终消息数: {final_stats['total_messages']}")
    print(f"   • 最终 Token 数: {final_stats['total_tokens']:,}")
    print(f"   • 压缩次数: {final_stats['total_compactions']}")
    print(f"   • 压缩是否触发: {'是' if final_stats['total_compactions'] > 0 else '否'}")
    print()

    if final_stats['total_compactions'] > 0:
        print("✅ 自动压缩功能正常工作！")
    else:
        print("⚠️  未触发压缩，可能需要更多消息或调整阈值")
    print()


if __name__ == "__main__":
    asyncio.run(test_compression())
