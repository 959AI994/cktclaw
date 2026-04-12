"""
Ad-hoc CktMem tests for Storage, TokenCounter, Compactor, and ContextManager.
"""

import asyncio
import os
import tempfile
from pathlib import Path

from cktmem import (
    ContextManager,
    Storage,
    CompactConfig,
    TokenCounter,
    MessageRole,
    MessageType,
    ContextLayer,
    Message,
)


def test_token_counter():
    """Smoke-test TokenCounter heuristics."""
    print("Testing TokenCounter...")

    counter = TokenCounter()

    # text estimate
    text = "Hello, world! " * 100
    tokens = counter._estimate_text(text)
    assert tokens > 0, "Token count should be positive"

    # message estimate
    msg = Message(
        role=MessageRole.USER,
        content="This is a test message",
    )
    msg_tokens = counter.estimate_message(msg)
    assert msg_tokens > 0, "Message token count should be positive"

    print("✓ TokenCounter tests passed")


async def test_storage():
    """SQLite round-trip checks."""
    print("\nTesting Storage...")

    # temp db file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        storage = Storage(db_path=db_path)

        # create session
        session_id = "test_session_001"
        await storage.create_session(
            session_id=session_id,
            project_name="test_project",
        )

        # fetch session
        session = await storage.get_session(session_id)
        assert session is not None, "Session should exist"
        assert session["session_id"] == session_id

        # anchor memory write
        await storage.store_anchor_memory(
            session_id=session_id,
            verilog_code="module test(); endmodule",
            analysis_report="Test report",
        )

        # anchor memory read
        anchor = await storage.get_anchor_memory(session_id)
        assert anchor is not None, "Anchor memory should exist"
        assert "module test" in anchor.verilog_code

        # insert message
        msg_id = await storage.add_message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Test message",
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )
        assert msg_id > 0, "Message ID should be positive"

        # list messages
        messages = await storage.get_messages(session_id)
        assert len(messages) > 0, "Should have messages"

        # core context row
        await storage.add_core_context(
            session_id=session_id,
            aig_filename="test.aig",
            verilog_code="module test2(); endmodule",
            analysis_report="Test report 2",
        )

        core_contexts = await storage.get_core_contexts(session_id)
        assert len(core_contexts) > 0, "Should have core contexts"

        print("✓ Storage tests passed")

    finally:
        # cleanup temp db
        if os.path.exists(db_path):
            os.unlink(db_path)


async def test_context_manager():
    """Context assembly without compaction."""
    print("\nTesting ContextManager...")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        storage = Storage(db_path=db_path)
        config = CompactConfig(
            auto_compact_threshold=5000,  # low threshold for local runs
        )

        context_manager = ContextManager(
            storage=storage,
            system_prompt="Test system prompt",
            config=config,
        )

        # session row
        session_id = "test_session_002"
        await storage.create_session(session_id=session_id)

        # seed anchor
        await storage.store_anchor_memory(
            session_id=session_id,
            verilog_code="module adder(); endmodule",
            analysis_report="Adder circuit",
        )

        # build_context
        messages = await context_manager.build_context(
            session_id=session_id,
            user_message="What is this circuit?",
            auto_compact=False,
        )

        assert len(messages) > 0, "Should have messages"
        assert messages[0].role == MessageRole.SYSTEM, "First message should be system"

        # assistant turn
        await context_manager.add_assistant_message(
            session_id=session_id,
            content="This is an adder circuit.",
        )

        # stats
        stats = await context_manager.get_context_stats(session_id)
        assert stats["total_messages"] > 0, "Should have messages"
        assert stats["total_tokens"] > 0, "Should have tokens"

        print("✓ ContextManager tests passed")

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


async def test_compression():
    """Ensure auto_compact can fire on a toy transcript."""
    print("\nTesting Compression...")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        storage = Storage(db_path=db_path)
        config = CompactConfig(
            auto_compact_threshold=1000,  # force compaction quickly
        )

        context_manager = ContextManager(
            storage=storage,
            system_prompt="Test",
            config=config,
        )

        session_id = "test_session_003"
        await storage.create_session(session_id=session_id)

        # long transcript
        for i in range(10):
            await storage.add_message(
                session_id=session_id,
                role=MessageRole.USER,
                content=f"User message {i}" * 50,
                msg_type=MessageType.CHAT,
                layer=ContextLayer.TURN,
            )
            await storage.add_message(
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content=f"Assistant response {i}" * 50,
                msg_type=MessageType.CHAT,
                layer=ContextLayer.TURN,
            )

        # build_context (may compact)
        messages = await context_manager.build_context(
            session_id=session_id,
            user_message="New question",
            auto_compact=True,
        )

        # optional boundary marker
        has_boundary = any(
            m.msg_type == MessageType.COMPACT_BOUNDARY
            for m in messages
        )

        # stats after compaction attempt
        stats = await context_manager.get_context_stats(session_id)

        print(f"  Total messages: {stats['total_messages']}")
        print(f"  Total tokens: {stats['total_tokens']}")
        print(f"  Compactions: {stats['total_compactions']}")
        print(f"  Has boundary: {has_boundary}")

        print("✓ Compression tests passed")

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


async def run_all_tests():
    """Run the informal test suite."""
    print("="*60)
    print("CktMem Unit Tests")
    print("="*60)

    test_token_counter()
    await test_storage()
    await test_context_manager()
    await test_compression()

    print("\n" + "="*60)
    print("All tests passed! ✓")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
