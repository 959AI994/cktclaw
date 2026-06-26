"""Tests for expanded full-chip toolchain wrappers."""

import asyncio

from cktclaw.eda_tools.tool_detection import detect_all_tools
from cktclaw.tools.base import ToolContext
from cktclaw.tools.eda.sby_tool import SbyTool
from cktclaw.tools.eda.slang_tool import SlangTool
from cktclaw.tools.eda.verible_tool import VeribleTool
from cktclaw.tools.eda.verilator_tool import VerilatorTool
from cktclaw.tools.eda.wolvrix_tool import WolvrixTool
from cktclaw.tools.registry import ToolRegistry


def test_expanded_tools_have_openai_schemas():
    tools = [VeribleTool(), SlangTool(), SbyTool(), VerilatorTool(), WolvrixTool()]
    for tool in tools:
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == tool.name
        assert schema["function"]["parameters"]["type"] == "object"


def test_auto_discover_builtin_finds_expanded_eda_tools():
    reg = ToolRegistry()
    reg.auto_discover_builtin()
    names = set(reg.list_names())
    for name in {"verible", "slang", "sby", "verilator", "wolvrix"}:
        assert name in names


def test_tool_detection_knows_expanded_tool_names():
    manifest = detect_all_tools()
    names = {tool.name for tool in manifest.tools}
    for name in {"verible-lint", "verible-format", "slang", "symbiyosys", "wolvrix"}:
        assert name in names


def test_missing_tool_failure_is_readable(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    ctx = ToolContext(working_dir=str(tmp_path))

    result = asyncio.run(VeribleTool().execute({
        "action": "lint",
        "files": ["missing.sv"],
    }, ctx))

    assert not result.success
    assert "Verible not found" in result.error
