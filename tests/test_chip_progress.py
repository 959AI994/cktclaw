"""Tests for chip automation progress events."""

from cktclaw.runtime.chip_progress import (
    publish_chip_progress,
    read_chip_progress,
    recent_chip_progress,
)


def test_progress_event_redacts_and_persists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from cktclaw.runtime.run_context import new_run

    run = new_run(kind="chiptest")
    with run.activate():
        event = publish_chip_progress(
            event_type="phase_started",
            run_id=run.run_id,
            phase="simulate",
            agent="eda_agent",
            skill="chip-autodesign",
            status="running",
            message="using sk-testsecret123",
            metadata={"api_key": "secret-value", "safe": "ok"},
        )

    assert event["message"] == "using [REDACTED]"
    assert event["metadata"]["api_key"] == "[REDACTED]"
    persisted = read_chip_progress(run.run_id)
    assert persisted[-1]["phase"] == "simulate"
    assert persisted[-1]["metadata"]["safe"] == "ok"


def test_autodesign_prepare_emits_structured_progress(tmp_path):
    from cktclaw.workflows.chip_autodesign import ChipAutoDesignController

    controller = ChipAutoDesignController(
        "design a sync fifo",
        project_dir=tmp_path / "fifo",
        force=True,
        mission_id="m-progress",
    )
    controller.prepare()

    events = [e for e in recent_chip_progress(limit=50) if e.get("mission_id") == "m-progress"]
    assert [e["event_type"] for e in events[-2:]] == ["run_started", "phase_completed"]
    assert events[-1]["phase"] == "spec_draft"
    assert events[-1]["skill"] == "chip-autodesign"


def test_mission_prepare_emits_agent_dag(tmp_path):
    from cktclaw.agents.mission_control import ChipMissionControl

    mission = ChipMissionControl(
        "design a sync fifo with verification and synthesis",
        project_dir=tmp_path / "mission",
        execute=False,
    )
    mission.prepare()

    events = [e for e in recent_chip_progress(limit=80) if e.get("mission_id") == mission.mission_id]
    assert events[0]["event_type"] == "run_started"
    dag = next(e for e in events if e["event_type"] == "agent_dag")
    roles = [step["role_id"] for step in dag["metadata"]["agent_plan"]]
    assert roles == ["pm_agent", "architect_agent", "eda_agent", "optimizer_agent"]


def test_web_orchestrator_state_records_chip_progress():
    from cktclaw.web.routers import orchestrator as orch

    run_id = "orch-test-progress"
    state = orch.OrchestratorRunState(
        run_id=run_id,
        skill="chip-mission",
        task="design fifo",
        session_id="s",
    )
    orch._orchestrator_runs[run_id] = state
    try:
        orch.record_chip_progress_event({
            "run_id": run_id,
            "event_type": "agent_dag",
            "phase": "pm_intake",
            "agent": "pm_agent",
            "status": "planned",
            "index": 1,
            "total": 4,
            "message": "planned",
            "metadata": {"agent_plan": [{"role_id": "pm_agent", "phase": "pm_intake"}]},
            "artifacts": ["/tmp/spec.md"],
        })
        orch.record_chip_progress_event({
            "run_id": run_id,
            "event_type": "run_completed",
            "phase": "signoff_report",
            "status": "PASS",
            "qor": {"num_cells": 12},
            "coverage": {"gaps": []},
            "message": "done",
        })
        data = orch._run_to_dict(state)
    finally:
        orch._orchestrator_runs.pop(run_id, None)

    assert data["status"] == "completed"
    assert data["agent_plan"][0]["role_id"] == "pm_agent"
    assert data["artifact_index"] == ["/tmp/spec.md"]
    assert data["qor_summary"]["num_cells"] == 12
    assert data["coverage_summary"]["gaps"] == []
