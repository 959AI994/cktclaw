"""Generic chip AutoDesign controller for RTL IP delivery."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...runtime.chip_progress import publish_chip_progress
from ..tiny_npu.flow import TinyNPUFlow, _parse_yosys_qor, _run_cmd
from .templates import spec_defaults_for, template_for
from .types import AutoDesignPlan, AutoDesignRunResult, AutoDesignSpec, FixRequest


STAGES = [
    "intent_parse",
    "spec_draft",
    "plan_review",
    "architecture",
    "rtl_generate",
    "tb_generate",
    "simulate",
    "coverage_gap",
    "repair_loop",
    "synth_qor",
    "signoff_report",
]


class ChipAutoDesignController:
    """End-to-end deterministic RTL IP flow with structured artifacts."""

    def __init__(
        self,
        user_task: str,
        *,
        project_dir: str | Path | None = None,
        max_iterations: int = 5,
        force: bool = False,
        cli_state: Any = None,
        progress_quiet: bool = False,
        progress_json: bool = False,
        mission_id: str = "",
    ) -> None:
        self.user_task = user_task.strip()
        self.max_iterations = max_iterations
        self.force = force
        self.cli_state = cli_state
        self.progress_quiet = progress_quiet
        self.progress_json = progress_json
        self.mission_id = mission_id
        self.design_kind = infer_design_kind(self.user_task)
        defaults = spec_defaults_for(self.design_kind, self.user_task)
        self.spec = AutoDesignSpec(
            design_kind=self.design_kind,
            module_name=defaults["module_name"],
            user_task=self.user_task,
            goal=defaults["goal"],
            interfaces=defaults["interfaces"],
            protocol=defaults["protocol"],
            parameters=defaults["parameters"],
            data_widths=defaults["data_widths"],
            ppa_targets={
                "primary": "correctness first",
                "synthesis": "generic Yosys QoR proxy",
            },
            inference_target=_inference_target_for(defaults["module_name"], self.user_task),
            verification_requirements=defaults["verification"],
            non_goals=[
                "No full SoC integration in V1",
                "No physical design or signoff timing/power without a liberty flow",
            ],
        )
        self.plan = AutoDesignPlan(
            stages=list(STAGES),
            tools=["iverilog", "vvp", "yosys"],
            file_layout={
                "spec": "spec.md",
                "plan": "plan.md",
                "rtl": "rtl/",
                "testbench": "tb/",
                "scripts": "scripts/",
                "reports": "reports/",
                "waveforms": "wave/",
                "synthesis": "synth/",
            },
            acceptance_gates=[
                "RTL compiles",
                "self-checking simulation prints ALL TESTS PASSED",
                "VCD waveform exists",
                "Yosys synthesis completes",
                "QoR JSON/report exists",
                "coverage gap report exists",
            ],
            risks=[
                "Line/toggle coverage depends on Verilator/lcov availability",
                "Frequency and power require liberty/OpenSTA/OpenROAD integration",
            ],
        )
        root = Path(project_dir) if project_dir else Path("runs") / "chip_autodesign" / self.spec.module_name
        self.project_dir = root.resolve()
        self.rtl_dir = self.project_dir / "rtl"
        self.tb_dir = self.project_dir / "tb"
        self.scripts_dir = self.project_dir / "scripts"
        self.build_dir = self.project_dir / "build"
        self.wave_dir = self.project_dir / "wave"
        self.synth_dir = self.project_dir / "synth"
        self.reports_dir = self.project_dir / "reports"
        self._prepared_paths: Optional[Dict[str, Path]] = None

    def _progress(
        self,
        event_type: str,
        phase: str,
        *,
        status: str = "",
        message: str = "",
        index: int = 0,
        artifacts: Optional[List[str]] = None,
        qor: Optional[Dict[str, Any]] = None,
        coverage: Optional[Dict[str, Any]] = None,
        fix_request: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        publish_chip_progress(
            event_type=event_type,
            cli_state=self.cli_state,
            mission_id=self.mission_id,
            phase=phase,
            agent="eda_agent",
            skill="chip-autodesign",
            status=status,
            index=index,
            total=len(STAGES),
            message=message,
            artifacts=artifacts,
            qor=qor,
            coverage=coverage,
            fix_request=fix_request,
            metadata={
                "design_kind": self.design_kind,
                "module_name": self.spec.module_name,
                "project_dir": str(self.project_dir),
                **(metadata or {}),
            },
            quiet=self.progress_quiet,
            json_progress=self.progress_json,
        )

    def prepare(self) -> Dict[str, Path]:
        """Write spec and plan artifacts before execution confirmation."""
        if self._prepared_paths is not None:
            return self._prepared_paths
        self._progress("run_started", "intent_parse", status="running", message=self.user_task, index=1)
        self._prepare_dirs()
        spec_path = self.project_dir / "spec.md"
        plan_path = self.project_dir / "plan.md"
        spec_path.write_text(render_spec(self.spec), encoding="utf-8")
        plan_path.write_text(render_plan(self.plan), encoding="utf-8")
        self._progress(
            "phase_completed",
            "spec_draft",
            status="PASS",
            message="Spec and plan artifacts prepared.",
            index=2,
            artifacts=[str(spec_path), str(plan_path)],
        )
        self._prepared_paths = {"spec": spec_path, "plan": plan_path}
        return self._prepared_paths

    async def run(self) -> AutoDesignRunResult:
        stages: Dict[str, Dict[str, Any]] = {}
        artifacts: List[str] = []
        fix_requests: List[FixRequest] = []

        prepared = self.prepare()
        artifacts.extend(str(p) for p in prepared.values())
        stages["intent_parse"] = _stage_ok(f"Detected design kind: {self.design_kind}")
        stages["spec_draft"] = _stage_ok("Wrote structured AutoDesignSpec.", artifact=str(prepared["spec"]))
        stages["plan_review"] = _stage_ok("Wrote executable AutoDesignPlan.", artifact=str(prepared["plan"]))
        stages["architecture"] = self._write_architecture()
        artifacts.append(str(self.project_dir / "architecture.md"))
        self._progress(
            "phase_completed",
            "architecture",
            status=stages["architecture"]["status"],
            message=stages["architecture"]["summary"],
            index=4,
            artifacts=[str(self.project_dir / "architecture.md")],
        )

        if self.design_kind == "tiny_npu_tile":
            return await self._run_tiny_npu(stages, artifacts)

        if self.design_kind == "custom":
            return await self._run_validated_rtl(stages, artifacts)

        template = template_for(self.spec)
        rtl_path = self.rtl_dir / template.rtl_filename
        tb_path = self.tb_dir / template.tb_filename
        rtl_path.write_text(template.rtl, encoding="utf-8")
        tb_path.write_text(template.tb, encoding="utf-8")
        artifacts.extend([str(rtl_path), str(tb_path)])
        stages["rtl_generate"] = _stage_ok(f"Generated RTL module {template.module_name}.", artifact=str(rtl_path))
        stages["tb_generate"] = _stage_ok("Generated self-checking SystemVerilog testbench.", artifact=str(tb_path))
        self._progress(
            "phase_completed",
            "rtl_generate",
            status="PASS",
            message=stages["rtl_generate"]["summary"],
            index=5,
            artifacts=[str(rtl_path)],
        )
        self._progress(
            "phase_completed",
            "tb_generate",
            status="PASS",
            message=stages["tb_generate"]["summary"],
            index=6,
            artifacts=[str(tb_path)],
        )

        self._progress("phase_started", "simulate", status="running", message="Running self-checking simulation.", index=7)
        sim = await self._run_simulation(template.rtl_filename, template.tb_filename, template.module_name)
        sim_attempts = 1
        while sim["status"] != "PASS" and sim_attempts < self.max_iterations:
            fix_requests.append(_fix_request("simulation", sim, str(tb_path), self._sim_command(template)))
            self._progress(
                "fix_requested",
                "repair_loop",
                status="running",
                message="Simulation failed; generated FixRequest and retrying.",
                index=9,
                fix_request=fix_requests[-1].to_dict(),
            )
            rtl_path.write_text(template.rtl, encoding="utf-8")
            tb_path.write_text(template.tb, encoding="utf-8")
            sim_attempts += 1
            sim = await self._run_simulation(template.rtl_filename, template.tb_filename, template.module_name)
        sim["attempts"] = sim_attempts
        stages["simulate"] = sim
        artifacts.extend(sim.get("artifacts", []))
        self._progress(
            "phase_completed" if sim["status"] == "PASS" else "phase_failed",
            "simulate",
            status=sim["status"],
            message=sim.get("summary", ""),
            index=7,
            artifacts=sim.get("artifacts", []),
        )
        if sim["status"] != "PASS":
            fix_requests.append(_fix_request("simulation", sim, str(tb_path), self._sim_command(template)))
            self._progress(
                "fix_requested",
                "repair_loop",
                status="failed",
                message="Simulation failed after retries.",
                index=9,
                fix_request=fix_requests[-1].to_dict(),
            )

        coverage = self._write_coverage_gap(template.functional_tests)
        stages["coverage_gap"] = coverage
        artifacts.append(str(self.reports_dir / "coverage_gap.md"))
        self._progress(
            "phase_completed",
            "coverage_gap",
            status=coverage["status"],
            message=coverage["summary"],
            index=8,
            artifacts=[str(self.reports_dir / "coverage_gap.md")],
            coverage={"functional_tests": coverage.get("functional_tests", []), "gaps": coverage.get("gaps", [])},
        )

        self._progress("phase_started", "synth_qor", status="running", message="Running Yosys synthesis/QoR.", index=10)
        synth = await self._run_synthesis(template.rtl_filename, template.module_name)
        synth_attempts = 1
        while synth["status"] != "PASS" and synth_attempts < self.max_iterations:
            fix_requests.append(_fix_request("synthesis", synth, str(rtl_path), f"yosys -s scripts/synth_yosys.ys"))
            self._progress(
                "fix_requested",
                "repair_loop",
                status="running",
                message="Synthesis failed; generated FixRequest and retrying.",
                index=9,
                fix_request=fix_requests[-1].to_dict(),
            )
            rtl_path.write_text(template.rtl, encoding="utf-8")
            synth_attempts += 1
            synth = await self._run_synthesis(template.rtl_filename, template.module_name)
        synth["attempts"] = synth_attempts
        stages["synth_qor"] = synth
        artifacts.extend(synth.get("artifacts", []))
        self._progress(
            "phase_completed" if synth["status"] == "PASS" else "phase_failed",
            "synth_qor",
            status=synth["status"],
            message=synth.get("summary", ""),
            index=10,
            artifacts=synth.get("artifacts", []),
            qor=synth.get("qor", {}),
        )
        if synth["status"] != "PASS":
            fix_requests.append(_fix_request("synthesis", synth, str(rtl_path), f"yosys -s scripts/synth_yosys.ys"))
            self._progress(
                "fix_requested",
                "repair_loop",
                status="failed",
                message="Synthesis failed after retries.",
                index=9,
                fix_request=fix_requests[-1].to_dict(),
            )

        if fix_requests:
            repair_status = "PASS" if sim["status"] == "PASS" and synth["status"] == "PASS" else "FAIL"
            stages["repair_loop"] = {
                "status": repair_status,
                "summary": (
                    f"Applied canonical template repair loop "
                    f"(simulation attempts={sim_attempts}, synthesis attempts={synth_attempts})."
                ),
                "fix_requests": [fr.to_dict() for fr in fix_requests],
            }
        else:
            stages["repair_loop"] = _stage_ok("No repair loop required; regression passed on first implementation.")
        self._progress(
            "phase_completed",
            "repair_loop",
            status=stages["repair_loop"]["status"],
            message=stages["repair_loop"].get("summary", ""),
            index=9,
            metadata={"fix_request_count": len(fix_requests)},
        )

        status = "PASS" if sim["status"] == "PASS" and synth["status"] == "PASS" else "FAIL"
        result = AutoDesignRunResult(
            status=status,
            project_dir=str(self.project_dir),
            spec=self.spec,
            plan=self.plan,
            stages=stages,
            artifacts=sorted(set(artifacts)),
            qor=synth.get("qor", {}),
            coverage_gaps=coverage.get("gaps", []),
            fix_requests=fix_requests,
        )
        stages["signoff_report"] = _stage_ok("Wrote final AutoDesign delivery report.")
        result.summary = self._write_final_report(result)
        result.artifacts.append(str(self.reports_dir / "autodesign_report.md"))
        self._progress(
            "run_completed" if result.status == "PASS" else "run_failed",
            "signoff_report",
            status=result.status,
            message="AutoDesign delivery report generated.",
            index=11,
            artifacts=[str(self.reports_dir / "autodesign_report.md")],
            qor=result.qor,
            coverage={"gaps": result.coverage_gaps},
        )
        return result

    async def _run_tiny_npu(
        self,
        stages: Dict[str, Dict[str, Any]],
        artifacts: List[str],
    ) -> AutoDesignRunResult:
        stages["rtl_generate"] = _stage_ok("Delegated Tiny NPU RTL generation to the reusable regression example.")
        stages["tb_generate"] = _stage_ok("Delegated Tiny NPU testbench generation to the reusable regression example.")
        self._progress("phase_started", "rtl_generate", status="running", message="Running Tiny NPU reusable regression.", index=5)
        tiny = await TinyNPUFlow(self.project_dir, force=False).run()
        stages["simulate"] = tiny.stages.get("simulation", {"status": "FAIL"})
        stages["coverage_gap"] = self._write_coverage_gap(
            tiny.stages.get("simulation", {}).get("coverage", {}).get("functional_tests", [])
        )
        stages["repair_loop"] = _stage_ok("No repair loop required." if tiny.status == "PASS" else "Tiny NPU run failed.")
        stages["synth_qor"] = tiny.stages.get("synthesis_qor", {"status": "FAIL"})
        stages["signoff_report"] = _stage_ok("Wrote final AutoDesign delivery report.")
        artifacts.extend(tiny.artifacts)
        artifacts.append(str(self.reports_dir / "coverage_gap.md"))
        result = AutoDesignRunResult(
            status=tiny.status,
            project_dir=str(self.project_dir),
            spec=self.spec,
            plan=self.plan,
            stages=stages,
            artifacts=sorted(set(artifacts)),
            qor=tiny.qor,
            coverage_gaps=stages["coverage_gap"].get("gaps", []),
            fix_requests=[],
        )
        result.summary = self._write_final_report(result)
        result.artifacts.append(str(self.reports_dir / "autodesign_report.md"))
        self._progress(
            "run_completed" if result.status == "PASS" else "run_failed",
            "signoff_report",
            status=result.status,
            message="Tiny NPU AutoDesign regression completed.",
            index=11,
            artifacts=result.artifacts[-12:],
            qor=result.qor,
            coverage={"gaps": result.coverage_gaps},
        )
        return result

    async def _run_validated_rtl(
        self,
        stages: Dict[str, Dict[str, Any]],
        artifacts: List[str],
    ) -> AutoDesignRunResult:
        from ..validated_rtl import ValidatedRTLController

        validated_dir = self.project_dir / "eda_validated_rtl"
        self._progress(
            "phase_started",
            "rtl_generate",
            status="running",
            message="Running validated RTL workflow via erie-verilog-generator facade.",
            index=5,
        )
        controller = ValidatedRTLController(
            self.user_task,
            project_dir=validated_dir,
            max_repair_rounds=self.max_iterations,
            use_mock_provider=os.environ.get("CKTCLAW_VALIDATED_RTL_MOCK", "").lower() in {"1", "true", "yes"},
            cli_state=self.cli_state,
            mission_id=self.mission_id,
            progress_quiet=self.progress_quiet,
            progress_json=self.progress_json,
            force=self.force,
        )
        validated = await controller.run()
        artifacts.extend(validated.artifacts)
        gate_status = {g.gate: g.status for g in validated.hard_gates}
        rtl_exists = gate_status.get("RTL exists", "FAIL")
        tb_exists = gate_status.get("TB exists", "FAIL")
        sim_status = gate_status.get("simulation PASS", "FAIL")
        synth_status = gate_status.get("Yosys synthesis PASS", "FAIL")
        stages["rtl_generate"] = {
            "status": "PASS" if rtl_exists == "PASS" else "FAIL",
            "summary": f"RTL hard gate: {rtl_exists} (workflow={validated.workflow_status}).",
            "artifact": str(validated_dir / "rtl"),
        }
        stages["tb_generate"] = {
            "status": "PASS" if tb_exists == "PASS" else "FAIL",
            "summary": f"TB hard gate: {tb_exists}.",
            "artifact": str(validated_dir / "tb"),
        }
        stages["simulate"] = {
            "status": "PASS" if sim_status == "PASS" else ("WARN" if sim_status == "tool_missing" else "FAIL"),
            "summary": f"Simulation hard gate: {sim_status}",
            "artifacts": [str(validated_dir / "reports" / "simulation.log")],
        }
        stages["coverage_gap"] = self._write_coverage_gap(
            [f"hard gate: {g.gate}={g.status}" for g in validated.hard_gates]
        )
        stages["repair_loop"] = {
            "status": "PASS" if not (validated.repair_state and validated.repair_state.escalated) else "FAIL",
            "summary": (
                f"Validated repair rounds={validated.repair_state.round_index if validated.repair_state else 0}; "
                f"escalated={validated.repair_state.escalated if validated.repair_state else False}"
            ),
        }
        stages["synth_qor"] = {
            "status": "PASS" if synth_status == "PASS" else ("WARN" if synth_status == "tool_missing" else "FAIL"),
            "summary": f"Synthesis gate: {synth_status}",
            "artifacts": [str(validated_dir / "reports" / "yosys.log")],
            "qor": {},
        }
        qor_path = validated_dir / "reports" / "qor.json"
        if qor_path.is_file():
            stages["synth_qor"]["qor"] = json.loads(qor_path.read_text(encoding="utf-8"))
        stages["signoff_report"] = _stage_ok("Merged validated RTL hard gate report into AutoDesign signoff.")
        result = AutoDesignRunResult(
            status="PASS" if validated.status == "PASS" else ("WARN" if validated.status == "WARN" else "FAIL"),
            project_dir=str(self.project_dir),
            spec=self.spec,
            plan=self.plan,
            stages=stages,
            artifacts=sorted(set(artifacts)),
            qor=stages["synth_qor"].get("qor", {}),
            coverage_gaps=stages["coverage_gap"].get("gaps", []),
            fix_requests=[],
        )
        if validated.report_path:
            result.artifacts.append(validated.report_path)
        result.summary = self._write_final_report(result)
        result.artifacts.append(str(self.reports_dir / "autodesign_report.md"))
        self._progress(
            "run_completed" if result.status == "PASS" else "run_failed",
            "signoff_report",
            status=result.status,
            message="Validated RTL AutoDesign completed.",
            index=11,
            artifacts=result.artifacts[-8:],
            qor=result.qor,
        )
        return result

    def _prepare_dirs(self) -> None:
        if self.project_dir.exists() and self.force:
            for child in self.project_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        for d in (
            self.rtl_dir,
            self.tb_dir,
            self.scripts_dir,
            self.build_dir,
            self.wave_dir,
            self.synth_dir,
            self.reports_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def _write_architecture(self) -> Dict[str, Any]:
        text = (
            f"# Architecture\n\n"
            f"Module: `{self.spec.module_name}`\n\n"
            f"Kind: `{self.spec.design_kind}`\n\n"
            f"Protocol: {self.spec.protocol}\n\n"
            f"The V1 AutoDesign implementation uses a local deterministic RTL template "
            f"selected from the parsed intent. The controller still records the same "
            f"spec, plan, verification, QoR, and repair artifacts that an LLM-backed "
            f"generator will consume in later revisions.\n"
        )
        path = self.project_dir / "architecture.md"
        path.write_text(text, encoding="utf-8")
        return _stage_ok("Wrote architecture decomposition.", artifact=str(path))

    async def _run_simulation(self, rtl_file: str, tb_file: str, module_name: str) -> Dict[str, Any]:
        iverilog = shutil.which("iverilog")
        vvp = shutil.which("vvp")
        if not iverilog or not vvp:
            return {"status": "FAIL", "summary": "iverilog/vvp not found.", "issues": ["Missing Icarus Verilog."]}
        out = self.build_dir / f"{module_name}_tb.vvp"
        cmd = [
            iverilog,
            "-g2012",
            "-Wall",
            "-o",
            str(out),
            str(self.rtl_dir / rtl_file),
            str(self.tb_dir / tb_file),
        ]
        compile_result = await _run_cmd(cmd, cwd=self.project_dir, timeout=120)
        if compile_result["returncode"] != 0:
            log = self.reports_dir / "simulation.log"
            log.write_text(compile_result["output"], encoding="utf-8")
            return {
                "status": "FAIL",
                "summary": "RTL/testbench compile failed.",
                "command": cmd,
                "output": compile_result["output"],
                "artifacts": [str(log)],
                "issues": ["Icarus compile failed."],
            }
        sim_result = await _run_cmd([vvp, str(out)], cwd=self.project_dir, timeout=120)
        log = self.reports_dir / "simulation.log"
        log.write_text(sim_result["output"], encoding="utf-8")
        passed = sim_result["returncode"] == 0 and "ALL TESTS PASSED" in sim_result["output"]
        return {
            "status": "PASS" if passed else "FAIL",
            "summary": "Self-checking simulation passed." if passed else "Self-checking simulation failed.",
            "command": [cmd, [vvp, str(out)]],
            "output": sim_result["output"],
            "artifacts": [str(log), str(out), str(self.wave_dir / f"{module_name}.vcd")],
            "issues": [] if passed else ["Simulation did not report ALL TESTS PASSED."],
        }

    async def _run_synthesis(self, rtl_file: str, module_name: str) -> Dict[str, Any]:
        yosys = shutil.which("yosys")
        if not yosys:
            return {"status": "FAIL", "summary": "yosys not found.", "issues": ["Missing Yosys."]}
        script = self.scripts_dir / "synth_yosys.ys"
        script.write_text(
            "\n".join([
                f"read_verilog -sv rtl/{rtl_file}",
                f"hierarchy -top {module_name}",
                "proc",
                "opt",
                "memory",
                "opt",
                "techmap",
                "opt",
                "stat",
                f"write_json synth/{module_name}.json",
                f"write_verilog synth/{module_name}_netlist.v",
                "",
            ]),
            encoding="utf-8",
        )
        result = await _run_cmd([yosys, "-s", str(script)], cwd=self.project_dir, timeout=180)
        log = self.reports_dir / "yosys.log"
        log.write_text(result["output"], encoding="utf-8")
        qor = _parse_yosys_qor(result["output"])
        qor_path = self.reports_dir / "qor.json"
        qor_path.write_text(json.dumps(qor, indent=2, ensure_ascii=False), encoding="utf-8")
        passed = result["returncode"] == 0 and qor.get("num_cells", 0) > 0
        return {
            "status": "PASS" if passed else "FAIL",
            "summary": (
                f"Yosys synthesis produced {qor.get('num_cells', 0)} generic cells."
                if passed else
                "Yosys synthesis failed or QoR was not parseable."
            ),
            "command": [yosys, "-s", str(script)],
            "qor": qor,
            "output": result["output"][-5000:],
            "artifacts": [
                str(script),
                str(log),
                str(qor_path),
                str(self.synth_dir / f"{module_name}.json"),
                str(self.synth_dir / f"{module_name}_netlist.v"),
            ],
            "issues": [] if passed else ["Yosys failed or produced no cells."],
        }

    def _sim_command(self, template) -> str:
        return f"iverilog -g2012 -Wall -o build/{template.module_name}_tb.vvp rtl/{template.rtl_filename} tb/{template.tb_filename}; vvp build/{template.module_name}_tb.vvp"

    def _write_coverage_gap(self, functional_tests: List[str]) -> Dict[str, Any]:
        has_verilator = shutil.which("verilator") is not None
        gaps = []
        if not has_verilator:
            gaps.append("Line/toggle coverage not collected because Verilator is not available in PATH.")
        gaps.append("Functional coverage is represented by the explicit self-checking test checklist in V1.")
        text = [
            "# Coverage Gap Report",
            "",
            "## Functional Checks",
            "",
        ]
        for item in functional_tests:
            text.append(f"- {item}")
        text.extend(["", "## Gaps", ""])
        for gap in gaps:
            text.append(f"- {gap}")
        path = self.reports_dir / "coverage_gap.md"
        path.write_text("\n".join(text) + "\n", encoding="utf-8")
        return {
            "status": "PASS",
            "summary": "Wrote functional coverage checklist and open coverage gaps.",
            "functional_tests": functional_tests,
            "gaps": gaps,
            "artifact": str(path),
        }

    def _write_final_report(self, result: AutoDesignRunResult) -> str:
        path = self.reports_dir / "autodesign_report.md"
        lines = [
            "# Chip AutoDesign Delivery Report",
            "",
            f"Status: **{result.status}**",
            f"Project: `{result.project_dir}`",
            f"Design kind: `{self.spec.design_kind}`",
            f"Module: `{self.spec.module_name}`",
            "",
            "## Stage Results",
            "",
        ]
        for name in STAGES:
            stage = result.stages.get(name, {})
            if stage:
                lines.append(f"- `{name}`: {stage.get('status')} - {stage.get('summary', '')}")
        lines.extend([
            "",
            "## QoR",
            "",
            "```json",
            json.dumps(result.qor, indent=2, ensure_ascii=False),
            "```",
            "",
            "## Coverage Gaps",
            "",
        ])
        for gap in result.coverage_gaps:
            lines.append(f"- {gap}")
        lines.extend(["", "## Fix Requests", ""])
        if result.fix_requests:
            for fr in result.fix_requests:
                lines.append(f"- `{fr.failure_type}`: {fr.suspected_root_cause}")
        else:
            lines.append("- None")
        lines.extend(["", "## Artifacts", ""])
        for artifact in result.artifacts:
            lines.append(f"- `{artifact}`")
        text = "\n".join(lines) + "\n"
        path.write_text(text, encoding="utf-8")
        return text


def infer_design_kind(user_task: str) -> str:
    text = user_task.lower()
    if re.search(r"\b(axi.?lite|axil|register block|reg.?block|寄存器)\b", text):
        return "axi_lite_reg_block"
    if re.search(r"\b(dsp|mac|multiply.?accumulate|乘加|乘累加)\b", text):
        return "signed_dsp_mac"
    if re.search(r"\b(tiny[_\s.-]?npu|npu.?tile|mnist|handwritten|手写|数字手势|手势识别|16\s*[x×]\s*16)\b", text):
        return "tiny_npu_tile"
    if re.search(
        r"\b(crc|stream.?accel|accelerator ip|custom ip|模块名[为是:\s]+[`']?[a-z][a-z0-9_]*[`']?)\b",
        user_task,
        re.IGNORECASE,
    ):
        return "custom"
    if re.search(r"模块名[为是:\s]+[`']?([A-Za-z_][A-Za-z0-9_]*)[`']?", user_task):
        return "custom"
    return "sync_fifo"


def _inference_target_for(module_name: str, user_task: str) -> Dict[str, Any]:
    text = user_task.lower()
    if module_name == "tiny_npu_tile_16x16" or re.search(r"(tiny[_\s.-]?npu|手势|digit\s*6|数字\s*6)", text):
        return {
            "scenario": "4x4 handwritten digit prototype inference",
            "target_digit": 6,
            "expected_result": "classifier output argmax == 6",
            "acceptance_gate": "digit_6_recognition PASS in self-checking simulation",
        }
    return {}


def render_spec(spec: AutoDesignSpec) -> str:
    return (
        f"# AutoDesign Spec\n\n"
        f"## Goal\n{spec.goal}\n\n"
        f"## User Task\n{spec.user_task}\n\n"
        f"## Module\n- name: `{spec.module_name}`\n- kind: `{spec.design_kind}`\n\n"
        f"## Interface\n"
        + "\n".join(f"- {i['name']}: {i['signals']}" for i in spec.interfaces)
        + f"\n\n## Protocol\n{spec.protocol}\n\n"
        f"## Clock and Reset\n{spec.clock_reset}\n\n"
        f"## Parameters\n```json\n{json.dumps(spec.parameters, indent=2, ensure_ascii=False)}\n```\n\n"
        f"## Verification Requirements\n"
        + "\n".join(f"- {v}" for v in spec.verification_requirements)
        + f"\n\n## Inference Target\n```json\n{json.dumps(spec.inference_target, indent=2, ensure_ascii=False)}\n```\n"
        + f"\n\n## Non Goals\n"
        + "\n".join(f"- {n}" for n in spec.non_goals)
        + "\n"
    )


def render_plan(plan: AutoDesignPlan) -> str:
    return (
        "# AutoDesign Execution Plan\n\n"
        "## Stages\n"
        + "\n".join(f"- {s}" for s in plan.stages)
        + "\n\n## Tools\n"
        + "\n".join(f"- {t}" for t in plan.tools)
        + "\n\n## Acceptance Gates\n"
        + "\n".join(f"- {g}" for g in plan.acceptance_gates)
        + "\n\n## Risks\n"
        + "\n".join(f"- {r}" for r in plan.risks)
        + f"\n\n## Fallback Strategy\n{plan.fallback_strategy}\n"
    )


def _stage_ok(summary: str, **extra: Any) -> Dict[str, Any]:
    data = {"status": "PASS", "summary": summary}
    data.update(extra)
    return data


def _fix_request(
    failure_type: str,
    stage: Dict[str, Any],
    target_file: str,
    regression_command: str,
) -> FixRequest:
    output = str(stage.get("output", ""))
    return FixRequest(
        failure_type=failure_type,
        log_excerpt=output[-1200:],
        suspected_root_cause="Generated implementation or testbench failed an executable gate.",
        target_file=target_file,
        suggested_change="Inspect the failing log excerpt, patch the target file, then rerun the regression command.",
        regression_command=regression_command,
    )
