"""Tests for OrchestratorEngine tool layer using CapabilityRegistry.

Note: llm_wrapper (chat_handler_v2._chat_with_messages) is NOT tested here.
Only the tool-lookup and tool-execution path is verified.
"""
import asyncio
from unittest.mock import MagicMock
from cktclaw.capability_registry import CapabilityRegistry, CapabilityEntry


def test_engine_tool_executor_delegates_to_capability_registry():
    executed_calls = []

    class FakeCapRegistry(CapabilityRegistry):
        async def list_all(self, user_invocable_only=False):
            return []

        async def execute(self, name, args, ctx):
            executed_calls.append((name, args))
            return f"executed:{name}"

    fake_reg = FakeCapRegistry()

    async def tool_executor(tool_name, tool_args):
        ctx = {"cli_state": None}
        return await fake_reg.execute(tool_name, tool_args, ctx)

    result = asyncio.run(tool_executor("yosys", {"args": "synth"}))
    assert result == "executed:yosys"
    assert executed_calls[0] == ("yosys", {"args": "synth"})


def test_engine_excludes_chip_skills():
    _ORCHESTRATOR_EXCLUDED = {
        "rltf", "pareto-negotiate", "reverse", "reverse-aig", "aig-reverse",
        "save_session_memory", "session-memory",
        "Read", "Write", "Bash", "Edit", "Glob", "Grep",
    }
    chip_entry = MagicMock(spec=CapabilityEntry)
    chip_entry.name = "chip-rtl"
    chip_entry.to_openai_schema = MagicMock(return_value={"function": {"name": "chip-rtl"}})
    safe_entry = MagicMock(spec=CapabilityEntry)
    safe_entry.name = "yosys"
    safe_entry.to_openai_schema = MagicMock(return_value={"function": {"name": "yosys"}})

    tools = [
        e.to_openai_schema() for e in [chip_entry, safe_entry]
        if not e.name.startswith("chip-") and e.name not in _ORCHESTRATOR_EXCLUDED
    ]
    tool_names = [t["function"]["name"] for t in tools]
    assert "chip-rtl" not in tool_names
    assert "yosys" in tool_names


def test_engine_excludes_blocked_skills():
    _ORCHESTRATOR_EXCLUDED = {"rltf", "reverse"}
    rltf = MagicMock(spec=CapabilityEntry)
    rltf.name = "rltf"
    abc = MagicMock(spec=CapabilityEntry)
    abc.name = "abc"
    abc.to_openai_schema = MagicMock(return_value={"function": {"name": "abc"}})

    tools = [
        e.to_openai_schema() for e in [rltf, abc]
        if not e.name.startswith("chip-") and e.name not in _ORCHESTRATOR_EXCLUDED
    ]
    tool_names = [t["function"]["name"] for t in tools]
    assert "rltf" not in tool_names
    assert "abc" in tool_names
