"""Tests for Agent Roster Registry."""

from pathlib import Path

import pytest

from cktclaw.agents.roster_registry import (
    AgentRosterRegistry,
    get_roster,
    reset_roster_for_tests,
    _normalize_role_id,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_roster_for_tests()
    yield
    reset_roster_for_tests()


def test_normalize_role_id_aliases():
    assert _normalize_role_id("PMAgent") == "pm_agent"
    assert _normalize_role_id("eda_agent") == "eda_agent"
    assert _normalize_role_id("ArchitectAgent") == "architect_agent"
    assert _normalize_role_id("RTLRepairAgent") == "rtl_repair_agent"
    assert _normalize_role_id("PPAOptimizerAgent") == "ppa_optimizer_agent"


def test_builtin_roster_loads_core_and_specialist_roles():
    roster = AgentRosterRegistry()
    roster.load()
    roles = roster.list_roles()
    assert len(roles) >= 12
    assert "pm_agent" in roles
    assert "eda_agent" in roles
    assert "optimizer_agent" in roles
    assert "rtl_repair_agent" in roles
    assert "analog_agent" in roles
    assert "hls_agent" in roles


def test_get_pm_agent_spec():
    roster = AgentRosterRegistry()
    roster.load()
    spec = roster.get("pm_agent")
    assert spec is not None
    assert spec.execution_mode == "coordinator"
    assert spec.model_tier == "orchestrator"
    assert "PMAgent" in spec.system_prompt


def test_eda_agent_is_orchestrator_meta():
    roster = AgentRosterRegistry()
    roster.load()
    spec = roster.get("eda_agent")
    assert spec is not None
    assert spec.execution_mode == "orchestrator_meta"
    assert "chip-rtl" in spec.mapped_skills
    assert "chip-synthesis" in spec.mapped_skills


def test_project_agent_override(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "PMAgent.md").write_text(
        "---\nrole_id: pm_agent\ndisplay_name: Custom PM\ndescription: override\n---\nCustom prompt body.\n",
        encoding="utf-8",
    )
    roster = AgentRosterRegistry()
    roster.load(extra_dirs=[tmp_path])
    spec = roster.get("pm_agent")
    assert spec is not None
    assert spec.display_name == "Custom PM"
    assert "Custom prompt" in spec.system_prompt


def test_register_project_agent_dict():
    roster = AgentRosterRegistry()
    roster.load()
    roster.register_project_agent({
        "name": "PMAgent",
        "description": "from workspace",
        "system_prompt": "Workspace PM prompt.",
        "source_path": "/tmp/x.md",
    })
    spec = roster.get("pm_agent")
    assert spec is not None
    assert "Workspace PM" in spec.system_prompt


def test_roster_summary_contains_all_agents():
    roster = AgentRosterRegistry()
    roster.load()
    summary = roster.roster_summary()
    assert "Agent Roster" in summary
    for name in ("PMAgent", "EDAAgent", "OptimizerAgent", "RTLRepairAgent"):
        assert name in summary


def test_get_roster_singleton():
    r1 = get_roster()
    r2 = get_roster()
    assert r1 is r2
    assert len(r1.list_roles()) >= 12
