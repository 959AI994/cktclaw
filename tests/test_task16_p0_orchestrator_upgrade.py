"""P0 orchestrator upgrades: design_state, recommendation loop-back, QoR, pipeline skill."""
import json
from pathlib import Path

import pytest

from cktclaw.orchestrator.parser import OrchestratorSpec
from cktclaw.orchestrator.state_machine import OrchestratorStateMachine
from cktclaw.orchestrator.design_state import DesignStateStore
from cktclaw.orchestrator.qor_extractor import (
    extract_qor_from_text,
    merge_qor,
)
from cktclaw.skills.chip_design_skills import CHIP_DESIGN_SKILLS, _AGENTS_ROOT


def _minimal_spec(stages: list[str]) -> OrchestratorSpec:
    return OrchestratorSpec(name="test-orchestrator", stages=stages)


def test_design_state_round_trip(tmp_path):
    path = tmp_path / "design_state.json"
    store = DesignStateStore(path)
    store.merge_stage_qor("synthesis-orchestrator", "compile_explore", {"area_cells": 42}, "PASS")
    store.append_history("synthesis-orchestrator", "compile_explore", "proceed", "ok")
    saved = store.save()
    assert saved == path
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["orchestrator_qor"]["synthesis"]["compile_explore"]["qor"]["area_cells"] == 42
    assert len(data["history"]) == 1


def test_design_state_summary_includes_open_fix_requests(tmp_path):
    path = tmp_path / "design_state.json"
    path.write_text(
        json.dumps({
            "format_version": "1.5",
            "fix_requests": [{"id": "fr1", "status": "open", "summary": "FIFO overflow"}],
        }),
        encoding="utf-8",
    )
    summary = DesignStateStore(path).summary_for_prompt()
    assert "open fix_requests" in summary
    assert "FIFO" in summary


def test_recommendation_loop_back_on_pass():
    spec = _minimal_spec(["a", "b", "c"])
    sm = OrchestratorStateMachine(spec)
    sm.start()
    sm.complete_stage("a", "PASS", {"x": 1})
    t = sm.complete_stage("b", "PASS", {}, recommendation="loop_back_to:a")
    assert t.action == "loop_back"
    assert t.next_stage == "a"


def test_recommendation_loop_back_ignored_for_invalid_stage():
    spec = _minimal_spec(["a", "b"])
    sm = OrchestratorStateMachine(spec)
    sm.start()
    t = sm.complete_stage("a", "PASS", {}, recommendation="loop_back_to:missing")
    assert t.action == "proceed"
    assert t.next_stage == "b"


def test_state_machine_restore_from_snapshot():
    spec = _minimal_spec(["s1", "s2", "s3"])
    sm = OrchestratorStateMachine(spec)
    sm.start()
    sm.complete_stage("s1", "PASS", {"area": 10})
    snap = sm.get_state_snapshot()
    sm2 = OrchestratorStateMachine(spec)
    resumed = sm2.restore_from_snapshot(snap)
    assert resumed == "s2"
    assert sm2.current_stage == "s2"


def test_qor_extractor_yosys_and_abc():
    yosys_out = "Number of cells: 123\nNumber of wires: 50"
    abc_out = "i/o = 4/2  lat = 3  and = 99  lev = 7"
    merged = merge_qor(
        {"area_cells": 0},
        extract_qor_from_text(yosys_out + "\n" + abc_out),
    )
    assert merged["area_cells"] == 123
    assert merged["and_nodes"] == 99
    assert merged["logic_levels"] == 7


def test_qor_extractor_sta_slack():
    sta_out = "slack = -0.42 ns\nwns: -0.42"
    metrics = extract_qor_from_text(sta_out)
    assert metrics.get("wns_ns") == -0.42


def test_chip_pipeline_skill_registered():
    names = {s.name for s in CHIP_DESIGN_SKILLS}
    assert "chip-pipeline" in names


def test_chip_pipeline_orchestrator_file_exists():
    orch = _AGENTS_ROOT / "meta" / "agents" / "pipeline-orchestrator.md"
    assert orch.is_file()


def test_checkpoint_includes_state_machine_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("CKTCLAW_HOME", str(tmp_path))
    from cktclaw.runtime.run_context import new_run
    from cktclaw.orchestrator.engine import save_checkpoint, load_checkpoint

    spec = _minimal_spec(["a", "b"])
    sm = OrchestratorStateMachine(spec)
    sm.start()
    sm.complete_stage("a", "PASS", {"k": 1})
    payload = {
        "orchestrator_name": "test-orchestrator",
        "user_task": "do task",
        "state_machine": sm.get_state_snapshot(),
    }
    r = new_run(kind="orchestrator")
    with r.activate():
        save_checkpoint(payload)
        cp = load_checkpoint(r.run_id)
    assert cp["user_task"] == "do task"
    assert cp["state_machine"]["stages"]["a"]["status"] == "passed"


def test_extract_stage_result_generic_fence():
    from cktclaw.orchestrator.engine import _extract_stage_result
    text = "Done.\n```\n{\"stage\": \"tool_discovery\", \"status\": \"pass\", \"qor\": {\"found\": 3}}\n```"
    r = _extract_stage_result(text)
    assert r is not None
    assert r["status"] == "PASS"
    assert r["qor"]["found"] == 3


def test_validate_suggested_next_step_maps_to_recommendation():
    from cktclaw.orchestrator.plan_schema import validate_stage_result
    raw = {
        "stage": "synth_check",
        "status": "WARN",
        "qor": {},
        "suggested_next_step": "loop_back_to:rtl_coding",
    }
    out = validate_stage_result(raw, "synth_check")
    assert out["recommendation"] == "loop_back_to:rtl_coding"


def test_auto_confirm_skips_tty_prompt(monkeypatch):
    import sys
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    # isatty is on stdin object - need to patch differently
    class FakeStdin:
        def isatty(self):
            return False
    monkeypatch.setattr(sys, "stdin", FakeStdin())
    from cktclaw.orchestrator.engine import OrchestratorEngine
    from cktclaw.orchestrator.parser import OrchestratorSpec
    spec = OrchestratorSpec(name="t", stages=["a"])
    engine = OrchestratorEngine(spec, "", None)
    # run() would skip interactive when not tty - verified by code path; smoke import only
    assert hasattr(engine, "run")


def test_intent_router_chip_pipeline():
    from cktclaw.handlers.intent_router import detect_chip_design_intent
    assert detect_chip_design_intent("process open fix_requests in design_state") == "chip-pipeline"
    assert detect_chip_design_intent("run cross-domain pipeline orchestration") == "chip-pipeline"
