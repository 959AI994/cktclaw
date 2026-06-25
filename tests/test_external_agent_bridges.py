"""Tests for optional external full-chip skill bridges."""

import asyncio
import importlib


def test_hls_generator_bridge_imports_without_dependency_repo():
    mod = importlib.import_module("cktclaw.skills.hls_generator_skill")
    assert hasattr(mod, "register_hls_generator_skill")


def test_hls_generator_register_skips_missing_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("HLS_GENERATOR_ROOT", str(tmp_path / "missing-hls-generator"))
    mod = importlib.reload(importlib.import_module("cktclaw.skills.hls_generator_skill"))
    assert asyncio.run(mod.register_hls_generator_skill()) == 0


def test_analog_design_bridge_imports_without_dependency_repo():
    mod = importlib.import_module("cktclaw.skills.analog_design_skills")
    assert hasattr(mod, "register_analog_design_skills")
    assert isinstance(mod.ANALOG_DESIGN_SKILLS, list)


def test_rtl_repair_skill_executor_returns_contract():
    mod = importlib.import_module("cktclaw.skills.rtl_repair_skill")
    result = asyncio.run(mod.rtl_repair_executor("fix adder.sv compile error", {}))
    assert result
    assert "RTL Repair Workflow" in result[0]["text"]
    assert "Verification evidence" in result[0]["text"]
