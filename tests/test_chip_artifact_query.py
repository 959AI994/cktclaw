import json

from cktclaw.handlers.chip_artifact_resolver import (
    render_artifact_query_for_cli,
    resolve_chip_artifact_query,
)
from cktclaw.handlers.chip_intent_router import ChipIntentRouter, execution_skill_for_intent
from cktclaw.handlers.schemas import ArtifactQuery


def test_artifact_query_resolves_design_state_artifacts(tmp_path, monkeypatch):
    rtl_dir = tmp_path / "runs" / "chip_mission" / "cfb9f8834c73" / "eda_autodesign" / "rtl"
    report_dir = tmp_path / "runs" / "chip_mission" / "cfb9f8834c73" / "eda_autodesign" / "reports"
    rtl_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    rtl = rtl_dir / "tiny_npu_tile_16x16.sv"
    sim = report_dir / "simulation.log"
    rtl.write_text("module tiny_npu_tile_16x16; endmodule\n", encoding="utf-8")
    sim.write_text("\n".join(f"line {i}" for i in range(150)), encoding="utf-8")

    state_path = tmp_path / "design_state.json"
    state_path.write_text(json.dumps({
        "mission": {
            "last_chip_mission_id": "cfb9f8834c73",
            "last_project_dir": str(tmp_path / "runs" / "chip_mission" / "cfb9f8834c73"),
            "artifacts_index": {
                "rtl": str(rtl),
                "simulation_log": str(sim),
                "autodesign_project_dir": str(tmp_path / "runs" / "chip_mission" / "cfb9f8834c73" / "eda_autodesign"),
            },
            "phases": [],
        }
    }), encoding="utf-8")
    monkeypatch.setenv("CHIP_DESIGN_STATE_PATH", str(state_path))

    query = resolve_chip_artifact_query(ArtifactQuery(kind="simulation_log"))
    assert query.last_chip_mission_id == "cfb9f8834c73"
    assert query.resolved_paths == [str(sim)]
    rendered = render_artifact_query_for_cli(query)
    assert str(sim) in rendered
    assert "line 149" in rendered


def test_artifact_query_missing_returns_missing(tmp_path, monkeypatch):
    state_path = tmp_path / "design_state.json"
    state_path.write_text(json.dumps({"mission": {"artifacts_index": {}, "phases": []}}), encoding="utf-8")
    monkeypatch.setenv("CHIP_DESIGN_STATE_PATH", str(state_path))

    query = resolve_chip_artifact_query(ArtifactQuery(kind="rtl"), context={"disable_fallback_scan": True})
    assert query.resolved_paths == []
    assert query.missing_artifacts == ["rtl"]
    assert "Artifact missing" in render_artifact_query_for_cli(query)


def test_artifact_query_router_priority_over_verification():
    import asyncio

    intent = asyncio.run(ChipIntentRouter().resolve_async("展示仿真结果"))
    assert intent.intent_type == "chip_artifact_query"
    assert intent.route == "chip-artifact-query"
    assert execution_skill_for_intent(intent) is None
