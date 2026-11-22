"""Tests for PM-led Chip Mission Control."""

import asyncio

from cktclaw.agents.mission_control import (
    ChipMissionControl,
    build_agent_plan,
    classify_mission,
    failure_specialist_for,
)


def test_mission_classification():
    assert classify_mission("design a sync fifo with verification and synthesis") == "rtl_ip_autodesign"
    assert classify_mission("create a Tiny NPU Tile for handwritten digit inference") == "rtl_ip_autodesign"
    assert classify_mission("design a CRC offload IP with verification") == "rtl_ip_autodesign"
    assert classify_mission("write coverage and formal checks for this fifo") == "verification_only"
    assert classify_mission("build an HLS kernel and FPGA emulation") == "hls_fpga"
    assert classify_mission("build an AXI-lite register block and driver plan") == "system_soc"
    assert classify_mission("plan analog layout and SPICE simulation") == "analog_pd_handoff"


def test_agent_plan_for_rtl_ip_uses_seven_agent_roles():
    plan = build_agent_plan("rtl_ip_autodesign", "design fifo")
    roles = [step.role_id for step in plan]
    assert roles == ["pm_agent", "architect_agent", "eda_agent", "optimizer_agent"]
    assert "chip-autodesign" in plan[2].skills


def test_failure_dispatch_rules():
    assert failure_specialist_for("Icarus simulation failed") == "rtl_repair_agent"
    assert failure_specialist_for("formal property proof failed") == "formal_agent"
    assert failure_specialist_for("Yosys QoR regression") == "ppa_optimizer_agent"
    assert failure_specialist_for("HLS schedule failed") == "hls_agent"
    assert failure_specialist_for("missing deployment tool") == "deploy_agent"


def test_mission_prepare_writes_design_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mission = ChipMissionControl(
        "create a Tiny NPU Tile for handwritten digit inference",
        project_dir=tmp_path / "mission",
        execute=False,
    )
    paths = mission.prepare()
    assert paths["mission_spec"].is_file()
    assert paths["agent_plan"].is_file()

    from cktclaw.orchestrator.design_state import DesignStateStore

    data = DesignStateStore().load()
    assert data["mission"]["status"] == "planned"
    assert data["mission"]["mission_spec"]["mission_type"] == "rtl_ip_autodesign"
    assert data["mission"]["mission_spec"]["intent"]["is_chip_task"] is True


def test_mission_prepare_for_unknown_ip_records_intent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mission = ChipMissionControl(
        "build a systolic sparse attention block for inference",
        project_dir=tmp_path / "attention",
        execute=False,
    )
    paths = mission.prepare()
    spec_text = paths["mission_spec"].read_text(encoding="utf-8")
    assert mission.mission_type == "rtl_ip_autodesign"
    assert mission.intent.route == "chip-mission"
    assert "Chip Intent" in spec_text


def test_chip_mission_fifo_integration(tmp_path):
    async def _run():
        from cktclaw.skills.chip_autodesign_skill import register_chip_autodesign_skill

        await register_chip_autodesign_skill()
        mission = ChipMissionControl(
            "design a sync fifo with verification and synthesis",
            project_dir=tmp_path / "mission",
            force=True,
        )
        return await mission.run()

    result = asyncio.run(_run())
    assert result.status == "PASS"
    assert result.mission_type == "rtl_ip_autodesign"
    assert any(p.role_id == "eda_agent" and p.status == "completed" for p in result.phases)
    assert (tmp_path / "mission" / "mission_report.md").is_file()


def test_chip_mission_skill_executor(tmp_path):
    async def _run():
        from cktclaw.skills.chip_autodesign_skill import register_chip_autodesign_skill
        from cktclaw.skills.chip_mission_skill import chip_mission_executor, register_chip_mission_skill

        await register_chip_autodesign_skill()
        await register_chip_mission_skill()
        return await chip_mission_executor(
            f"design a sync fifo with verification and synthesis --yes --project-dir {tmp_path / 'skill'} --force",
            {},
        )

    result = asyncio.run(_run())
    assert result[1]["type"] == "chip_mission_result"
    assert result[1]["result"]["status"] == "PASS"
