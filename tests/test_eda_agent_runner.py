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
    calls = []

    async def fake_execute(name, args, ctx):
        calls.append(name)
        return f"ok from {name}"

    async def _run():
        with patch("cktclaw.capability_registry.get_capability_registry") as mock_reg:
            mock_reg.return_value.execute = fake_execute
            runner = EDAAgentRunner()
            return await runner.run("design adder", context={})

    result = asyncio.run(_run())
    assert result["status"] == "completed"
    assert len(calls) == len(DEFAULT_EDA_CHAIN)
    assert calls[0] == "chip-rtl"


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


def test_eda_runner_skips_optional_pd_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def fake_execute(name, args, ctx):
        if name == "chip-pd":
            raise RuntimeError("pd optional fail")
        return "ok"

    async def _run():
        with patch("cktclaw.capability_registry.get_capability_registry") as mock_reg:
            mock_reg.return_value.execute = fake_execute
            return await EDAAgentRunner().run("design adder", context={})

    result = asyncio.run(_run())
    assert result["status"] == "completed"
