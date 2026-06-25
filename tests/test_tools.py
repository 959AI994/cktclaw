"""
Tests for Tool Registry and BaseTool.
"""

import asyncio
from typing import Any, Dict

import pytest

from cktclaw.tools.base import BaseTool, ToolContext, ToolResult
from cktclaw.tools.registry import ToolRegistry
from cktclaw.tools.schema import to_openai_tools, to_anthropic_tools


class DummyTool(BaseTool):
    """Test tool for unit tests."""
    name = "dummy"
    description = "A test tool"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Test input"},
        },
        "required": ["input"],
    }
    read_only = True
    category = "test"

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult.ok(output=f"echo: {params.get('input', '')}")


class FailingTool(BaseTool):
    """Tool that always fails."""
    name = "failing"
    description = "Always fails"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult.fail("intentional failure")


class TestToolResult:
    def test_ok_result(self):
        r = ToolResult.ok("success")
        assert r.success is True
        assert r.output == "success"
        assert r.error is None

    def test_fail_result(self):
        r = ToolResult.fail("bad", output="partial")
        assert r.success is False
        assert r.error == "bad"
        assert r.output == "partial"


class TestBaseTool:
    def test_validate_params_required(self):
        tool = DummyTool()
        err = tool.validate_params({})
        assert err is not None
        assert "input" in err

    def test_validate_params_ok(self):
        tool = DummyTool()
        err = tool.validate_params({"input": "hello"})
        assert err is None

    def test_openai_schema(self):
        tool = DummyTool()
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "dummy"
        assert "input" in schema["function"]["parameters"]["properties"]

    def test_anthropic_schema(self):
        tool = DummyTool()
        schema = tool.to_anthropic_schema()
        assert schema["name"] == "dummy"
        assert "input_schema" in schema

    def test_execute(self):
        tool = DummyTool()
        ctx = ToolContext(session_id="test")
        result = asyncio.run(tool.execute({"input": "world"}, ctx))
        assert result.success
        assert "world" in result.output


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = DummyTool()
        reg.register(tool)
        assert reg.get("dummy") is tool

    def test_has(self):
        reg = ToolRegistry()
        reg.register(DummyTool())
        assert reg.has("dummy")
        assert not reg.has("nonexistent")

    def test_unregister(self):
        reg = ToolRegistry()
        reg.register(DummyTool())
        assert reg.unregister("dummy")
        assert not reg.has("dummy")

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(DummyTool())
        reg.register(FailingTool())
        tools = reg.list_tools()
        assert len(tools) == 2

    def test_list_by_category(self):
        reg = ToolRegistry()
        reg.register(DummyTool())
        reg.register(FailingTool())
        test_tools = reg.list_by_category("test")
        assert len(test_tools) == 1
        assert test_tools[0].name == "dummy"

    def test_list_read_only(self):
        reg = ToolRegistry()
        reg.register(DummyTool())
        reg.register(FailingTool())
        ro = reg.list_read_only()
        assert len(ro) == 1
        assert ro[0].name == "dummy"

    def test_openai_tools(self):
        reg = ToolRegistry()
        reg.register(DummyTool())
        schemas = reg.get_openai_tools()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "dummy"

    def test_unregister_by_source(self):
        reg = ToolRegistry()
        reg.register(DummyTool(), source="plugin:test")
        reg.register(FailingTool(), source="builtin")
        removed = reg.unregister_by_source("plugin:test")
        assert removed == 1
        assert not reg.has("dummy")
        assert reg.has("failing")

    def test_no_duplicate_register(self):
        reg = ToolRegistry()
        reg.register(DummyTool())
        reg.register(DummyTool())  # Should warn but not overwrite
        assert len(reg.list_tools()) == 1


class TestSchemaConversion:
    def test_to_openai(self):
        tools = [DummyTool()]
        schemas = to_openai_tools(tools)
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"

    def test_to_anthropic(self):
        tools = [DummyTool()]
        schemas = to_anthropic_tools(tools)
        assert len(schemas) == 1
        assert "input_schema" in schemas[0]
