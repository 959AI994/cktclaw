"""Tests for MultiAgentOrchestrator seven-agent pipeline."""

import asyncio
from unittest.mock import patch

import pytest


def _mock_result(role_id: str, status="completed", output="ok"):
    return {
        "role_id": role_id,
        "status": status,
        "output": f"{role_id} output: {output}",
        "artifacts": [],
        "error": None,
    }


def test_full_pipeline_phase_order():
    calls = []

    async def fake_run(role_id, task, context=None):
        calls.append(role_id)
        return _mock_result(role_id)

    async def _run():
        from cktclaw.agents.multi_agent_orchestrator import MultiAgentOrchestrator
        with patch(
            "cktclaw.agents.runners.specialist_runner.run_specialist_role",
            side_effect=fake_run,
        ):
            orch = MultiAgentOrchestrator(max_optimization_rounds=0)
            return await orch.run("design SoC accelerator", mode="full")

    result = asyncio.run(_run())
    assert result.status in ("completed", "completed_with_warnings")
    assert calls[0] == "pm_agent"
    assert "architect_agent" in calls
    assert "eda_agent" in calls
    assert "compiler_agent" in calls
    assert "runtime_agent" in calls
    assert "deploy_agent" in calls
    assert "optimizer_agent" in calls


def test_eda_only_mode():
    async def fake_run(role_id, task, context=None):
        return _mock_result(role_id)

    async def _run():
        from cktclaw.agents.multi_agent_orchestrator import MultiAgentOrchestrator
        with patch(
            "cktclaw.agents.runners.specialist_runner.run_specialist_role",
            side_effect=fake_run,
        ):
            return await MultiAgentOrchestrator().run("rtl only", mode="eda_only")

    result = asyncio.run(_run())
    assert len(result.phases) == 2
    assert result.phases[-1].role_id == "eda_agent"


def test_spec_written_to_design_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def fake_run(role_id, task, context=None):
        return _mock_result(role_id, output="spec content here")

    async def _run():
        from cktclaw.agents.multi_agent_orchestrator import MultiAgentOrchestrator
        with patch(
            "cktclaw.agents.runners.specialist_runner.run_specialist_role",
            side_effect=fake_run,
        ):
            await MultiAgentOrchestrator(max_optimization_rounds=0).run(
                "test", mode="eda_only",
            )

    asyncio.run(_run())
    from cktclaw.orchestrator.design_state import DesignStateStore
    data = DesignStateStore().load()
    assert data.get("spec", {}).get("markdown")
