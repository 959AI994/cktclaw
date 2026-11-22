"""Tests for EDAAgent meta-coordinator runner."""

import asyncio
from unittest.mock import patch

import pytest

from cktclaw.agents.runners.eda_agent_runner import EDAAgentRunner, DEFAULT_EDA_CHAIN
from cktclaw.orchestrator.design_state import DesignStateStore


def test_eda_chain_order():
    assert DEFAULT_EDA_CHAIN[0] == "chip-rtl"
    assert "chip-synthesis" in DEFAULT_EDA_CHAIN


def test_eda_runner_completes_all_steps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dut = tmp_path / "dut.sv"
    dut.write_text("module dut; endmodule\n", encoding="utf-8")
    calls = []

    class _OkSkill:
        async def executor(self, task, ctx):
            calls.append(task[:20])
            return [{"type": "text", "text": f"ok from {task[:12]}"}]

    class _Entry:
        def __init__(self, name):
            self.skill_obj = _OkSkill()
            self.name = name

    async def fake_get(name):
        calls.append(name)
        return _Entry(name)

    async def _run():
        with patch("cktclaw.capability_registry.get_capability_registry") as mock_reg:
            mock_reg.return_value.get = fake_get
            runner = EDAAgentRunner()
            return await runner.run("design adder", context={"dut_path": str(dut)})

    result = asyncio.run(_run())
    assert result["status"] == "completed"
    assert len(calls) >= len(DEFAULT_EDA_CHAIN)
    assert "chip-rtl" in calls


def test_eda_runner_fix_request_on_required_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def fake_execute(name, args, ctx):
        if name == "chip-rtl":
            raise RuntimeError("rtl failed")
        return "ok"

    async def _run():
        with patch("cktclaw.capability_registry.get_capability_registry") as mock_reg:
            mock_reg.return_value.execute = fake_execute
            return await EDAAgentRunner().run("design adder", context={})

    result = asyncio.run(_run())
    assert result["status"] == "failed"
    data = DesignStateStore().load()
    assert any(fr.get("status") == "open" for fr in data.get("fix_requests", []))


def test_eda_runner_dispatches_specialist_when_enabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dispatched = []

    async def fake_execute(name, args, ctx):
        if name == "chip-rtl":
            raise RuntimeError("rtl failed")
        return "ok"

    async def fake_specialist(role_id, task, *, context=None):
        dispatched.append((role_id, task))
        return {
            "role_id": role_id,
            "status": "completed",
            "output": "repair proposal",
            "artifacts": [],
            "error": None,
        }

    async def _run():
        with patch("cktclaw.capability_registry.get_capability_registry") as mock_reg:
            mock_reg.return_value.execute = fake_execute
            with patch(
                "cktclaw.agents.runners.specialist_runner.run_specialist_role",
                fake_specialist,
            ):
                return await EDAAgentRunner().run(
                    "design adder",
                    context={"enable_specialist_repair": True},
                )

    result = asyncio.run(_run())
    assert result["status"] == "failed"
    assert dispatched
    assert dispatched[0][0] == "rtl_repair_agent"
    assert any(step.get("status") == "specialist_dispatched" for step in result["steps"])
    assert (
        "SPECIALIST_DISPATCH stage=chip-rtl agent=rtl_repair_agent status=completed"
        in result["output"]
    )


def test_eda_runner_dispatches_specialist_on_skill_failure_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dispatched = []

    class _FailSkill:
        async def executor(self, task, ctx):
            return [{
                "type": "text",
                "text": "## chip-autodesign\n**Status:** FAIL\nChip AutoDesign failed: sim",
            }]

    class _Entry:
        skill_obj = _FailSkill()

    async def fake_get(name):
        return _Entry()

    async def fake_specialist(role_id, task, *, context=None):
        dispatched.append(role_id)
        return {
            "role_id": role_id,
            "status": "completed",
            "output": "repair proposal",
            "artifacts": [],
            "error": None,
        }

    async def _run():
        with patch("cktclaw.capability_registry.get_capability_registry") as mock_reg:
            mock_reg.return_value.get = fake_get
            with patch(
                "cktclaw.agents.runners.specialist_runner.run_specialist_role",
                fake_specialist,
            ):
                return await EDAAgentRunner(chain=["chip-autodesign"]).run(
                    "design crc8",
                    context={"enable_specialist_repair": True},
                )

    result = asyncio.run(_run())
    assert result["status"] == "failed"
    assert dispatched
    assert dispatched[0] == "rtl_repair_agent"
    assert any(step.get("status") == "specialist_dispatched" for step in result["steps"])


def test_eda_runner_skips_optional_pd_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dut = tmp_path / "dut.sv"
    dut.write_text("module dut; endmodule\n", encoding="utf-8")

    class _OkSkill:
        async def executor(self, task, ctx):
            return [{"type": "text", "text": "ok"}]

    class _Entry:
        def __init__(self, skill):
            self.skill_obj = skill

    async def fake_get(name):
        if name == "chip-pd":
            class _FailSkill:
                async def executor(self, task, ctx):
                    raise RuntimeError("pd optional fail")
            return _Entry(_FailSkill())
        return _Entry(_OkSkill())

    async def _run():
        with patch("cktclaw.capability_registry.get_capability_registry") as mock_reg:
            mock_reg.return_value.get = fake_get
            return await EDAAgentRunner().run("design adder", context={"dut_path": str(dut)})

    result = asyncio.run(_run())
    assert result["status"] == "completed"


def test_eda_runner_does_not_start_verification_without_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CHIP_DESIGN_STATE_PATH", str(tmp_path / "design_state.json"))
    calls = []

    async def fake_execute(name, args, ctx):
        calls.append(name)
        return "ok"

    async def _run():
        with patch("cktclaw.capability_registry.get_capability_registry") as mock_reg:
            mock_reg.return_value.execute = fake_execute
            return await EDAAgentRunner(chain=["chip-verification"]).run(
                "跑一下这个模块的 testbench",
                context={"disable_fallback_scan": True},
            )

    result = asyncio.run(_run())
    assert result["status"] == "failed"
    assert calls == []
    assert "DUT RTL" in result["output"]
