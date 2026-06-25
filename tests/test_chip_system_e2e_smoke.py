"""E2E smoke tests for chip-system skill (mocked specialists)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from cktclaw.skills.chip_system_skill import chip_system_executor, _parse_args


def test_parse_args_eda_only():
    goal, mode = _parse_args("design fifo --eda-only")
    assert mode == "eda_only"
    assert "fifo" in goal


def test_chip_system_executor_empty_args():
    result = asyncio.run(chip_system_executor("", {}))
    assert "Usage" in result[0]["text"]


def test_chip_system_executor_mock_pipeline():
    mock_result = type("R", (), {
        "session_id": "abc",
        "status": "completed",
        "phases": [],
        "spec_markdown": "# Spec",
        "optimization_rounds": 0,
        "needs_iteration": False,
        "to_dict": lambda self: {"status": "completed"},
    })()

    async def _run():
        with patch(
            "cktclaw.agents.multi_agent_orchestrator.MultiAgentOrchestrator",
        ) as MockOrch:
            MockOrch.return_value.run = AsyncMock(return_value=mock_result)
            return await chip_system_executor("design adder 8bit", {"cli_state": None})

    out = asyncio.run(_run())
    assert out[0]["type"] == "text"
    assert "Chip System" in out[0]["text"]
    assert out[1]["type"] == "multi_agent_result"


def test_intent_routes_chip_system():
    from cktclaw.handlers.intent_router import detect_chip_design_intent_with_confidence

    route = detect_chip_design_intent_with_confidence(
        "从架构到部署完成 8 位加法器全栈设计流程"
    )
    assert route is not None
    assert route["skill_id"] == "chip-system"
    assert route["confidence"] >= 0.85
