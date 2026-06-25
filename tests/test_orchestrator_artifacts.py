"""Tests for orchestrator completion artifacts and reports."""

import json
from pathlib import Path

from cktclaw.orchestrator.artifacts import (
    build_completion_report,
    collect_artifacts,
    detect_qor_warnings,
    enrich_snapshot_with_artifacts,
    parse_task_workdir,
)


def test_parse_task_workdir_from_chinese_and_relative_paths():
    task = "设计 8 位加法器，工作目录：./designs/adder_8bit/"
    assert parse_task_workdir(task) == Path("./designs/adder_8bit/")

    task2 = "Implement FIFO under ./designs/fifo_sync/"
    assert parse_task_workdir(task2) == Path("./designs/fifo_sync/")


def test_collect_artifacts_from_task_dir_and_run_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    workdir = tmp_path / "designs" / "adder_8bit"
    workdir.mkdir(parents=True)
    sv = workdir / "adder_8bit.sv"
    sv.write_text("module adder_8bit(); endmodule\n", encoding="utf-8")
    fl = workdir / "filelist.f"
    fl.write_text(f"{sv.name}\n", encoding="utf-8")

    run_dir = tmp_path / "run1"
    ws = run_dir / "workspace"
    ws.mkdir(parents=True)
    (ws / "synth.rpt").write_text("ok\n", encoding="utf-8")

    task = f"8-bit adder under {workdir.relative_to(tmp_path).as_posix()}/"
    artifacts = collect_artifacts(task=task, run_dir=run_dir)
    paths = {a.path for a in artifacts}
    assert str(sv.resolve()) in paths
    assert str(fl.resolve()) in paths
    assert str((ws / "synth.rpt").resolve()) in paths


def test_collect_artifacts_empty_when_no_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    task = "设计加法器，工作目录：./designs/missing/"
    assert collect_artifacts(task=task) == []


def test_detect_qor_warnings_yosys_error_on_passed_stage():
    snapshot = {
        "stages": {
            "synthesis_check": {
                "status": "passed",
                "qor": {"yosys_error": 1},
            }
        }
    }
    warnings = detect_qor_warnings(snapshot)
    assert len(warnings) == 1
    assert "yosys_error" in warnings[0]


def test_build_completion_report_with_and_without_artifacts():
    base_snapshot = {
        "finished": True,
        "current_stage": "rtl_signoff",
        "stage_order": ["module_planning", "rtl_signoff"],
        "stages": {
            "module_planning": {"status": "passed", "attempts": 1},
            "rtl_signoff": {"status": "passed", "attempts": 1},
        },
    }

    empty = enrich_snapshot_with_artifacts(base_snapshot, task="plan only")
    report_empty = build_completion_report(empty, skill="chip-rtl", task="plan only")
    assert "## Orchestrator 完成" in report_empty
    assert "未在任务目录" in report_empty
    assert "### 技术详情 (JSON)" in report_empty

    with_artifacts = dict(base_snapshot)
    with_artifacts["artifacts"] = [
        {"path": "./designs/adder_8bit/adder_8bit.sv", "kind": "systemverilog", "size": 128},
    ]
    with_artifacts["workdir"] = "./designs/adder_8bit/"
    with_artifacts["warnings"] = []
    report_full = build_completion_report(
        with_artifacts, skill="chip-rtl", task="adder", display_name="RTL Design",
    )
    assert "adder_8bit.sv" in report_full
    assert "6/6" not in report_full  # only 2 stages in fixture
    assert "2/2" in report_full

    warn_snap = dict(with_artifacts)
    warn_snap["warnings"] = ["阶段 `synthesis_check` 标记为通过，但 Yosys log 检测到 ERROR。"]
    report_warn = build_completion_report(warn_snap, skill="chip-rtl", task="adder")
    assert "⚠️" in report_warn

    # JSON section is valid-ish (extract between fences)
    start = report_full.index("```json") + len("```json\n")
    end = report_full.index("```", start)
    parsed = json.loads(report_full[start:end])
    assert parsed["finished"] is True
