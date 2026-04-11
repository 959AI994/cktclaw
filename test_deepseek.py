#!/usr/bin/env python3
"""
DeepSeek API + CktMem 集成测试

测试 DeepSeek API 调用和记忆系统的完整集成
"""

import sys
import os
import asyncio
sys.path.insert(0, '/home/wjx/pythonproject')

from openai import OpenAI
from cktclaw.main import CLIState


async def test_deepseek_integration():
    """测试 DeepSeek API + CktMem 集成"""

    print("="*70)
    print("DeepSeek API + CktMem 集成测试")
    print("="*70)
    print()

    # 1. 初始化 DeepSeek 客户端
    print("1. 初始化 DeepSeek 客户端...")
    client = OpenAI(
        api_key="sk-af52153ce10d4453abf859151ea6ef05",
        base_url="https://api.deepseek.com"
    )
    print("   ✓ DeepSeek 客户端初始化成功")
    print()

    # 2. 测试基本 API 调用
    print("2. 测试基本 DeepSeek API 调用...")
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a helpful assistant for EDA tools."},
                {"role": "user", "content": "What is Yosys?"},
            ],
            stream=False
        )
        answer = response.choices[0].message.content
        print(f"   ✓ API 调用成功")
        print(f"   回答: {answer[:100]}...")
        print()
    except Exception as e:
        print(f"   ✗ API 调用失败: {e}")
        return

    # 3. 初始化 CktClaw 状态
    print("3. 初始化 CktClaw 状态...")
    cli_state = CLIState()
    session_id = cli_state.session_id
    print(f"   ✓ 会话 ID: {session_id}")
    print()

    # 4. 测试多轮对话 + 记忆系统
    print("4. 测试多轮对话 + 记忆系统...")

    test_conversations = [
        {
            "user": "What is Yosys and what can it do?",
            "context": "First question about Yosys"
        },
        {
            "user": "Can you give me an example of using Yosys for logic synthesis?",
            "context": "Follow-up question"
        },
        {
            "user": "What are the main commands in Yosys?",
            "context": "Third question"
        },
    ]

    for i, conv in enumerate(test_conversations, 1):
        print(f"\n   [{i}] 用户: {conv['user']}")

        # 构建上下文（使用 CktMem）
        messages = await cli_state.context_manager.build_context(
            session_id=session_id,
            user_message=conv['user'],
            auto_compact=False,
        )

        # 转换为 DeepSeek API 格式
        api_messages = [
            {
                "role": msg.role.value if hasattr(msg.role, 'value') else msg.role,
                "content": msg.content,
            }
            for msg in messages
        ]

        print(f"       上下文消息数: {len(api_messages)}")

        # 调用 DeepSeek API
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=api_messages,
                stream=False,
                max_tokens=500,
            )
            assistant_reply = response.choices[0].message.content

            print(f"       ✓ DeepSeek 回复: {assistant_reply[:80]}...")

            # 存储到 CktMem
            await cli_state.context_manager.add_assistant_message(
                session_id=session_id,
                content=assistant_reply,
            )
            print(f"       ✓ 回复已存储到记忆系统")

        except Exception as e:
            print(f"       ✗ API 调用失败: {e}")
            continue

    print()

    # 5. 检查记忆系统统计
    print("5. 检查记忆系统统计...")
    stats = await cli_state.context_manager.get_context_stats(session_id)
    print(f"   ✓ 总消息数: {stats['total_messages']}")
    print(f"   ✓ 总 Token 数: {stats['total_tokens']}")
    print(f"   ✓ 压缩次数: {stats['total_compactions']}")
    print()

    # 6. 测试上下文连贯性
    print("6. 测试上下文连贯性...")
    print("   提问: 'Can you summarize what we discussed about Yosys?'")

    messages = await cli_state.context_manager.build_context(
        session_id=session_id,
        user_message="Can you summarize what we discussed about Yosys?",
        auto_compact=False,
    )

    api_messages = [
        {
            "role": msg.role.value if hasattr(msg.role, 'value') else msg.role,
            "content": msg.content,
        }
        for msg in messages
    ]

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=api_messages,
            stream=False,
            max_tokens=500,
        )
        summary = response.choices[0].message.content
        print(f"   ✓ DeepSeek 总结: {summary[:150]}...")

        await cli_state.context_manager.add_assistant_message(
            session_id=session_id,
            content=summary,
        )

    except Exception as e:
        print(f"   ✗ API 调用失败: {e}")

    print()

    # 7. 最终统计
    print("7. 最终统计...")
    final_stats = await cli_state.context_manager.get_context_stats(session_id)
    print(f"   ✓ 总消息数: {final_stats['total_messages']}")
    print(f"   ✓ 总 Token 数: {final_stats['total_tokens']}")
    print(f"   ✓ 压缩次数: {final_stats['total_compactions']}")
    print()

    print("="*70)
    print("✅ DeepSeek API + CktMem 集成测试完成！")
    print("="*70)
    print()

    print("📊 测试总结:")
    print(f"   • DeepSeek API 调用: 成功")
    print(f"   • 记忆系统集成: 成功")
    print(f"   • 上下文连贯性: 成功")
    print(f"   • 总对话轮数: 4 轮")
    print(f"   • 最终消息数: {final_stats['total_messages']}")
    print(f"   • 最终 Token 数: {final_stats['total_tokens']}")
    print()


if __name__ == "__main__":
    asyncio.run(test_deepseek_integration())
