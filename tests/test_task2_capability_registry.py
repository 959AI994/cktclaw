"""Tests for CapabilityRegistry facade."""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock


def _mock_tool(name="yosys", description="Yosys synth tool"):
    tool = MagicMock()
    tool.name = name
    tool.description = description
    result = MagicMock()
    result.output = "synth OK"
    tool.execute = AsyncMock(return_value=result)
    tool.to_openai_schema = MagicMock(return_value={
        "type": "function", "function": {"name": name, "description": description}
    })
    return tool


def _mock_skill(name="chip-rtl", description="RTL design skill"):
    skill = MagicMock()
    skill.name = name
    skill.description = description
    skill.user_invocable = True
    skill.executor = AsyncMock(return_value=[{"type": "text", "text": "RTL done"}])
    return skill


def _mock_tool_registry(tools: dict):
    reg = MagicMock()
    reg.get = lambda n: tools.get(n)
    reg.list_tools = lambda: tools
    return reg


def _mock_skill_registry(skills: list):
    reg = MagicMock()

    async def _get_skill(name):
        return next((s for s in skills if s.name == name), None)

    async def _list_skills():
        return skills

    reg.get_skill = _get_skill
    reg.list_skills = _list_skills
    return reg


def test_get_returns_tool_entry():
    from cktclaw.capability_registry import CapabilityRegistry
    reg = CapabilityRegistry()
    reg._tool_registry = _mock_tool_registry({"yosys": _mock_tool("yosys")})
    reg._skill_registry = _mock_skill_registry([])
    entry = asyncio.run(reg.get("yosys"))
    assert entry is not None and entry.source == "tool"


def test_get_falls_back_to_skill():
    from cktclaw.capability_registry import CapabilityRegistry
    reg = CapabilityRegistry()
    reg._tool_registry = _mock_tool_registry({})
    reg._skill_registry = _mock_skill_registry([_mock_skill("chip-rtl")])
    entry = asyncio.run(reg.get("chip-rtl"))
    assert entry is not None and entry.source == "skill"


def test_tool_takes_precedence_over_skill():
    from cktclaw.capability_registry import CapabilityRegistry
    reg = CapabilityRegistry()
    reg._tool_registry = _mock_tool_registry({"abc": _mock_tool("abc")})
    reg._skill_registry = _mock_skill_registry([_mock_skill("abc")])
    entry = asyncio.run(reg.get("abc"))
    assert entry.source == "tool"


def test_get_returns_none_for_unknown():
    from cktclaw.capability_registry import CapabilityRegistry
    reg = CapabilityRegistry()
    reg._tool_registry = _mock_tool_registry({})
    reg._skill_registry = _mock_skill_registry([])
    assert asyncio.run(reg.get("nonexistent")) is None


def test_list_all_combines_registries():
    from cktclaw.capability_registry import CapabilityRegistry
    reg = CapabilityRegistry()
    reg._tool_registry = _mock_tool_registry({"yosys": _mock_tool("yosys")})
    reg._skill_registry = _mock_skill_registry([_mock_skill("chip-rtl")])
    entries = asyncio.run(reg.list_all())
    names = {e.name for e in entries}
    assert "yosys" in names and "chip-rtl" in names


def test_execute_routes_to_tool():
    from cktclaw.capability_registry import CapabilityRegistry
    reg = CapabilityRegistry()
    tool = _mock_tool("yosys")
    reg._tool_registry = _mock_tool_registry({"yosys": tool})
    reg._skill_registry = _mock_skill_registry([])
    result = asyncio.run(reg.execute("yosys", {"args": "synth"}, MagicMock()))
    assert result == "synth OK"
    tool.execute.assert_called_once()


def test_execute_routes_to_skill():
    from cktclaw.capability_registry import CapabilityRegistry
    reg = CapabilityRegistry()
    reg._tool_registry = _mock_tool_registry({})
    skill = _mock_skill("chip-rtl")
    reg._skill_registry = _mock_skill_registry([skill])
    result = asyncio.run(reg.execute("chip-rtl", {"args": "design a FIFO"}, MagicMock()))
    assert "RTL done" in result


def test_get_capability_registry_returns_singleton():
    import cktclaw.capability_registry as mod
    mod._capability_registry = None
    reg1 = mod.get_capability_registry()
    reg2 = mod.get_capability_registry()
    assert reg1 is reg2


def test_tool_registry_error_falls_back_gracefully():
    from cktclaw.capability_registry import CapabilityRegistry
    reg = CapabilityRegistry()
    broken_reg = MagicMock()
    broken_reg.get = MagicMock(side_effect=RuntimeError("broken"))
    reg._tool_registry = broken_reg
    reg._skill_registry = _mock_skill_registry([_mock_skill("chip-rtl")])
    entry = asyncio.run(reg.get("chip-rtl"))
    assert entry is not None and entry.source == "skill"


def test_get_required_permissions_includes_capability_token():
    from cktclaw.capability_registry import get_capability_registry
    reg = get_capability_registry()
    perms = reg.get_required_permissions("bash")
    assert "system:exec" in perms
    assert any(p.startswith("capability:") for p in perms)
