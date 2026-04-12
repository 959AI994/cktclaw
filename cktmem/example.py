"""
Runnable examples for the legacy SQLite-backed CktMem stack.
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
    """End-to-end demo: session, anchor memory, turns, stats."""

    storage = Storage(db_path="example_sessions.db")
    config = CompactConfig(
        auto_compact_threshold=150_000,
        target_tokens=40_000,
    )

    system_prompt = """You are CktClaw, an AI assistant for circuit analysis.
You help users understand and analyze digital circuits."""

    context_manager = ContextManager(
        storage=storage,
        system_prompt=system_prompt,
        config=config,
    )

    session_id = "example_session_001"
    await storage.create_session(
        session_id=session_id,
        project_name="example_circuit",
        model_choice="logicrt",
    )

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

    user_inputs = [
        "What does this circuit implement?",
        "What are the input and output bit widths?",
        "Is overflow handled?",
    ]

    for user_input in user_inputs:
        print(f"\nuser: {user_input}")

        messages = await context_manager.build_context(
            session_id=session_id,
            user_message=user_input,
            auto_compact=True,
        )

        print(f"context_messages={len(messages)}")

        assistant_response = f"Stub answer for: {user_input!r}"

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

    await storage.add_core_context(
        session_id=session_id,
        aig_filename="multiplier.aig",
        verilog_code="module multiplier(...); ... endmodule",
        analysis_report="Multiplier circuit analysis...",
    )

    stats = await context_manager.get_context_stats(session_id)
    print("\n=== context stats ===")
    print(f"total_messages={stats['total_messages']}")
    print(f"total_tokens={stats['total_tokens']}")
    print(f"total_compactions={stats['total_compactions']}")
    print(f"last_compact_at={stats['last_compact_at']}")


async def example_manual_compact():
    """Populate many long rows, then force auto-compaction."""

    storage = Storage(db_path="example_sessions.db")
    config = CompactConfig()

    context_manager = ContextManager(
        storage=storage,
        system_prompt="System prompt...",
        config=config,
    )

    session_id = "example_session_002"
    await storage.create_session(session_id=session_id)

    for i in range(20):
        await storage.add_message(
            session_id=session_id,
            role=MessageRole.USER,
            content=f"User message {i}" * 100,
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

    messages = await context_manager.build_context(
        session_id=session_id,
        user_message="New question",
        auto_compact=True,
    )

    print(f"\npost_compact_message_count={len(messages)}")

    stats = await context_manager.get_context_stats(session_id)
    print(f"total_compactions={stats['total_compactions']}")


if __name__ == "__main__":
    print("=== CktMem examples ===\n")

    print("Example 1: basic flow")
    asyncio.run(example_usage())

    print("\n" + "=" * 50 + "\n")

    print("Example 2: auto compaction")
    asyncio.run(example_manual_compact())
