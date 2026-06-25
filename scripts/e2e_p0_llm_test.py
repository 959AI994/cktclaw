#!/usr/bin/env python3
"""
Real LLM end-to-end tests for P0 orchestrator (post-fix).

Usage:
  python scripts/e2e_p0_llm_test.py infra      # 2-stage infrastructure
  python scripts/e2e_p0_llm_test.py synthesis # full 5-stage synthesis
  python scripts/e2e_p0_llm_test.py all         # both
"""
import asyncio
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_ROOT.parent))

from cktclaw.main import CLIState
from cktclaw.orchestrator import parse_orchestrator, OrchestratorEngine, load_checkpoint
from cktclaw.orchestrator.design_state import DesignStateStore
from cktclaw.eda_tools.tool_detection import detect_all_tools
from cktclaw.runtime.run_context import new_run
from cktclaw.skills.chip_design_skills import _AGENTS_ROOT


def _paths(domain: str, skill_subdir: str, orch_file: str):
    base = _AGENTS_ROOT / domain
    return (
        base / "agents" / orch_file,
        base / "skills" / skill_subdir / "SKILL.md",
    )


async def run_orchestrator(
    domain: str,
    skill_subdir: str,
    orch_file: str,
    user_task: str,
    max_stages: int | None = None,
) -> dict:
    orch_path, skill_path = _paths(domain, skill_subdir, orch_file)
    spec = parse_orchestrator(orch_path)
    if max_stages is not None:
        spec.stages = spec.stages[:max_stages]
    skill_md = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""

    cli = CLIState()
    cli.current_engine = "deepseek"
    manifest = detect_all_tools()
    cli._tool_manifest = manifest

    run = new_run(kind="orchestrator")
    engine = OrchestratorEngine(spec, skill_md, cli, manifest, None)
    engine.design_state = DesignStateStore(run.dir / "design_state.json")

    report = {
        "name": spec.name,
        "stages": spec.stages,
        "run_id": run.run_id,
        "run_dir": str(run.dir),
        "user_task_input": user_task,
    }

    with run.activate():
        t0 = time.perf_counter()
        snapshot = await engine.run(user_task, auto_confirm=True)
        report["total_seconds"] = round(time.perf_counter() - t0, 2)

    cp = load_checkpoint(run.run_id)
    ds_path = engine.design_state.path
    ds = json.loads(ds_path.read_text(encoding="utf-8")) if ds_path.is_file() else {}

    report["user_task_checkpoint"] = cp.get("user_task") if cp else None
    report["snapshot"] = snapshot
    report["stages_detail"] = snapshot.get("stages", {})
    report["design_state_qor"] = ds.get("orchestrator_qor", {})
    report["history"] = ds.get("history", [])
    report["json_warn_stages"] = [
        s for s, info in report["stages_detail"].items()
        if any(
            "structured status" in str(h.get("reason", "")).lower()
            for h in report["history"]
            if h.get("stage") == s
        )
    ]
    # detect WARN from issues in rendered flow — check history reasons
    report["all_pass_or_real_json"] = all(
        info.get("status") == "passed"
        for info in report["stages_detail"].values()
    )
    return report


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    results = {}

    if mode in ("infra", "all"):
        print("\n" + "=" * 72)
        print("  E2E: infrastructure-orchestrator (tool_discovery + module_discovery)")
        print("=" * 72)
        results["infrastructure"] = await run_orchestrator(
            "infrastructure", "infrastructure", "infrastructure-orchestrator.md",
            "Detect available EDA tools on this host and summarize readiness for chip design.",
            max_stages=2,
        )

    if mode in ("synthesis", "all"):
        print("\n" + "=" * 72)
        print("  E2E: synthesis-orchestrator (FULL 5 stages)")
        print("=" * 72)
        results["synthesis"] = await run_orchestrator(
            "synthesis", "logic-synthesis", "synthesis-orchestrator.md",
            (
                "Synthesize a simple 4-bit adder in Verilog using Yosys on this host. "
                "Minimize area. Create a minimal adder.v if needed, run yosys synth, "
                "and report area_cells and logic levels in qor."
            ),
            max_stages=None,  # all 5 stages
        )

    print("\n" + "=" * 72)
    print("  E2E RESULTS JSON")
    print("=" * 72)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
