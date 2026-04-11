"""
CktMem 使用示例

演示如何在 CktClaw 中使用 cktmem 模块
"""

import asyncio
from cktmem import (
    ContextManager,
    Storage,
    CompactConfig,
    MessageRole,
    MessageType,
    ContextLayer,
)


async def example_usage():
    """示例：完整的使用流程"""

    # 1. 初始化存储和配置
    storage = Storage(db_path="example_sessions.db")
    config = CompactConfig(
        auto_compact_threshold=150_000,
        target_tokens=40_000,
    )

    # 2. 创建上下文管理器
    system_prompt = """You are CktClaw, an AI assistant for circuit analysis.
You help users understand and analyze digital circuits."""

    context_manager = ContextManager(
        storage=storage,
        system_prompt=system_prompt,
        config=config,
    )

    # 3. 创建会话
    session_id = "example_session_001"
    await storage.create_session(
        session_id=session_id,
        project_name="example_circuit",
        model_choice="logicrt",
    )

    # 4. 存储首份核心上下文（Anchor Memory）
    verilog_code = """
module adder(
    input [3:0] a,
    input [3:0] b,
    output [4:0] sum
);
    assign sum = a + b;
endmodule
"""

    analysis_report = """
Circuit Analysis Report:
- Module: adder
- Inputs: a[3:0], b[3:0]
- Outputs: sum[4:0]
- Function: 4-bit adder with carry output
"""

    await storage.store_anchor_memory(
        session_id=session_id,
        verilog_code=verilog_code,
        analysis_report=analysis_report,
    )

    # 5. 模拟用户对话
    user_inputs = [
        "这个电路实现什么功能？",
        "输入输出的位宽是多少？",
        "有没有溢出保护？",
    ]

    for user_input in user_inputs:
        print(f"\n用户: {user_input}")

        # 构建上下文（自动压缩）
        messages = await context_manager.build_context(
            session_id=session_id,
            user_message=user_input,
            auto_compact=True,
        )

        print(f"上下文消息数: {len(messages)}")

        # 模拟 LLM 响应
        assistant_response = f"这是对 '{user_input}' 的回答..."

        # 存储对话
        await storage.add_message(
            session_id=session_id,
            role=MessageRole.USER,
            content=user_input,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )
        await storage.add_message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=assistant_response,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )

    # 6. 添加后续电路分析（Core Context）
    await storage.add_core_context(
        session_id=session_id,
        aig_filename="multiplier.aig",
        verilog_code="module multiplier(...); ... endmodule",
        analysis_report="Multiplier circuit analysis...",
    )

    # 7. 获取统计信息
    stats = await context_manager.get_context_stats(session_id)
    print("\n=== 上下文统计 ===")
    print(f"总消息数: {stats['total_messages']}")
    print(f"总 Token 数: {stats['total_tokens']}")
    print(f"压缩次数: {stats['total_compactions']}")
    print(f"最后压缩时间: {stats['last_compact_at']}")


async def example_manual_compact():
    """示例：手动触发压缩"""

    storage = Storage(db_path="example_sessions.db")
    config = CompactConfig()

    context_manager = ContextManager(
        storage=storage,
        system_prompt="System prompt...",
        config=config,
    )

    session_id = "example_session_002"
    await storage.create_session(session_id=session_id)

    # 添加大量消息
    for i in range(20):
        await storage.add_message(
            session_id=session_id,
            role=MessageRole.USER,
            content=f"User message {i}" * 100,  # 长消息
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )
        await storage.add_message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=f"Assistant response {i}" * 100,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )

    # 构建上下文（触发自动压缩）
    messages = await context_manager.build_context(
        session_id=session_id,
        user_message="New question",
        auto_compact=True,
    )

    print(f"\n压缩后消息数: {len(messages)}")

    # 查看统计
    stats = await context_manager.get_context_stats(session_id)
    print(f"压缩次数: {stats['total_compactions']}")


if __name__ == "__main__":
    print("=== CktMem 使用示例 ===\n")

    print("示例 1: 基本使用流程")
    asyncio.run(example_usage())

    print("\n" + "="*50 + "\n")

    print("示例 2: 自动压缩")
    asyncio.run(example_manual_compact())
