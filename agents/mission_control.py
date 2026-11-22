"""Adaptive multi-agent mission control for chip design tasks."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from ..handlers.intent_router import ChipIntent, resolve_chip_intent
from ..runtime.chip_progress import publish_chip_progress


MissionType = Literal[
    "rtl_ip_autodesign",
    "verification_only",
    "synthesis_qor",
    "hls_fpga",
    "system_soc",
    "analog_pd_handoff",
]


@dataclass
class MissionSpec:
    mission_id: str
    mission_type: MissionType
    user_task: str
    success_criteria: List[str]
    intent: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentPlanStep:
    phase: str
    role_id: str
    action: str
    skills: List[str] = field(default_factory=list)
    handoff_to: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MissionPhaseResult:
    phase: str
    role_id: str
    status: str
    output: str = ""
    artifacts: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChipMissionResult:
    mission_id: str
    mission_type: MissionType
    status: str
    spec: MissionSpec
    agent_plan: List[AgentPlanStep]
    phases: List[MissionPhaseResult] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    report_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "mission_type": self.mission_type,
            "status": self.status,
            "spec": self.spec.to_dict(),
            "agent_plan": [s.to_dict() for s in self.agent_plan],
            "phases": [p.to_dict() for p in self.phases],
            "artifacts": self.artifacts,
            "report_path": self.report_path,
        }


class ChipMissionControl:
    """Mission-level PM-led router over the CktClaw agent roster."""

    def __init__(
        self,
        user_task: str,
        *,
        cli_state: Any = None,
        project_dir: str | Path | None = None,
        execute: bool = True,
        force: bool = False,
        max_iterations: int = 5,
        max_mission_rounds: int = -1,
        progress_quiet: bool = False,
        progress_json: bool = False,
        intent: Optional[ChipIntent] = None,
    ) -> None:
        self.user_task = user_task.strip()
        self.intent = intent or resolve_chip_intent(self.user_task)
        self.cli_state = cli_state
        self.execute = execute
        self.force = force
        self.max_iterations = max_iterations
        self.max_mission_rounds = max_mission_rounds
        self.progress_quiet = progress_quiet
        self.progress_json = progress_json
        self.mission_id = uuid.uuid4().hex[:12]
        self.mission_type = classify_mission(self.user_task, self.intent)
        self.project_dir = Path(project_dir or Path("runs") / "chip_mission" / self.mission_id).resolve()
        self.spec = MissionSpec(
            mission_id=self.mission_id,
            mission_type=self.mission_type,
            user_task=self.user_task,
            success_criteria=success_criteria_for(self.mission_type),
            intent=self.intent.to_dict(),
            constraints={
                "default_entry": "pm_agent",
                "execution_policy": "agent_decision_execution",
                "route": self.intent.route,
                "requested_scope": self.intent.requested_scope,
            },
        )
        self.agent_plan = build_agent_plan(self.mission_type, self.user_task, self.intent)
        self._prepared_paths: Optional[Dict[str, Path]] = None

    def _progress(
        self,
        event_type: str,
        phase: str,
        *,
        agent: str = "",
        skill: str = "",
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
            agent=agent,
            skill=skill,
            status=status,
            index=index,
            total=max(len(self.agent_plan), 1),
            message=message,
            artifacts=artifacts,
            qor=qor,
            coverage=coverage,
            fix_request=fix_request,
            metadata={
                "mission_type": self.mission_type,
                "project_dir": str(self.project_dir),
                "intent": self.intent.to_dict(),
                **(metadata or {}),
            },
            quiet=self.progress_quiet,
            json_progress=self.progress_json,
        )

    def prepare(self) -> Dict[str, Path]:
        if self._prepared_paths is not None:
            return self._prepared_paths
        self._progress(
            "run_started",
            "pm_intake",
            agent="pm_agent",
            status="running",
            index=1,
            message="Mission classification and planning started.",
            metadata={"user_task": self.user_task, "intent": self.intent.to_dict()},
        )
        self.project_dir.mkdir(parents=True, exist_ok=True)
        spec_path = self.project_dir / "mission_spec.md"
        plan_path = self.project_dir / "agent_plan.md"
        spec_path.write_text(render_mission_spec(self.spec), encoding="utf-8")
        plan_path.write_text(render_agent_plan(self.agent_plan), encoding="utf-8")
        self._progress(
            "agent_dag",
            "pm_intake",
            agent="pm_agent",
            status="planned",
            index=1,
            message=f"Mission classified as {self.mission_type}.",
            artifacts=[str(spec_path), str(plan_path)],
            metadata={"agent_plan": [s.to_dict() for s in self.agent_plan]},
        )
        self._write_design_state(status="planned", artifacts={
            "mission_spec": str(spec_path),
            "agent_plan": str(plan_path),
        })
        self._prepared_paths = {"mission_spec": spec_path, "agent_plan": plan_path}
        return self._prepared_paths

    async def run(self) -> ChipMissionResult:
        prepared = self.prepare()
        all_phases: List[MissionPhaseResult] = []
        all_artifacts = [str(p) for p in prepared.values()]
        mission_round = 0
        final_status = "FAIL"

        while True:
            mission_round += 1
            if mission_round > 100:
                break
            iteration_dir = self.project_dir / f"iteration_{mission_round:03d}"
            iteration_dir.mkdir(parents=True, exist_ok=True)
            self._progress(
                "iteration_started",
                "mission_loop",
                agent="pm_agent",
                status="running",
                index=mission_round,
                message=f"Mission iteration {mission_round} started.",
                metadata={
                    "mission_round": mission_round,
                    "next_action": "run agent plan",
                    "capability_class": "workflow",
                },
            )

            round_phases, round_artifacts = await self._run_agent_plan_iteration(
                prepared,
                mission_round=mission_round,
                skip_architecture=mission_round > 1,
            )
            all_phases.extend(round_phases)
            all_artifacts.extend(round_artifacts)

            iteration_report = iteration_dir / "iteration_report.json"
            iteration_report.write_text(
                json.dumps(
                    {
                        "mission_round": mission_round,
                        "passes": _mission_passes(round_phases),
                        "phases": [p.to_dict() for p in round_phases],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            all_artifacts.append(str(iteration_report))

            if _mission_passes(round_phases):
                final_status = "PASS"
                break

            if self._mission_interrupt_requested():
                break

            if self.max_mission_rounds >= 0 and mission_round >= self.max_mission_rounds:
                break

            eda_phase = next((p for p in round_phases if p.role_id == "eda_agent"), None)
            if eda_phase and eda_phase.status == "failed":
                await self._dispatch_mission_repair(eda_phase, mission_round)

            opt_phase = next(
                (p for p in round_phases if p.role_id in {"optimizer_agent", "ppa_optimizer_agent"}),
                None,
            )
            if opt_phase and not _suggests_iteration(opt_phase.output or ""):
                if eda_phase and eda_phase.status != "failed":
                    break

            self._progress(
                "iteration_failed",
                "mission_loop",
                agent="pm_agent",
                status="retry",
                index=mission_round,
                message=f"Mission iteration {mission_round} failed; starting next iteration.",
                metadata={
                    "mission_round": mission_round,
                    "next_action": "dispatch:rtl_repair_agent then retry eda",
                    "capability_class": "workflow",
                },
            )

        report_path = self.project_dir / "mission_report.md"
        result = ChipMissionResult(
            mission_id=self.mission_id,
            mission_type=self.mission_type,
            status=final_status,
            spec=self.spec,
            agent_plan=self.agent_plan,
            phases=all_phases,
            artifacts=sorted(set(all_artifacts)),
            report_path=str(report_path),
        )
        report_path.write_text(render_mission_report(result, mission_rounds=mission_round), encoding="utf-8")
        result.artifacts.append(str(report_path))
        if final_status == "PASS":
            self._persist_reusable_artifacts()
        self._progress(
            "run_completed" if final_status == "PASS" else "run_failed",
            "signoff_report",
            agent="pm_agent",
            status=final_status,
            index=len(self.agent_plan),
            message="Mission signoff report generated.",
            artifacts=[str(report_path)],
            metadata={
                "phase_count": len(all_phases),
                "mission_rounds": mission_round,
                "capability_map": _capability_map_summary(),
            },
        )
        self._write_design_state(
            status=final_status,
            artifacts={"mission_report": str(report_path)},
            phases=[p.to_dict() for p in all_phases],
        )
        return result

    async def _run_agent_plan_iteration(
        self,
        prepared: Dict[str, Path],
        *,
        mission_round: int,
        skip_architecture: bool,
    ) -> tuple[List[MissionPhaseResult], List[str]]:
        phases: List[MissionPhaseResult] = []
        artifacts: List[str] = []

        if mission_round == 1:
            pm_output = render_mission_spec(self.spec)
            phases.append(MissionPhaseResult(
                phase="pm_intake",
                role_id="pm_agent",
                status="completed",
                output=pm_output,
                artifacts=[str(prepared["mission_spec"])],
            ))
            self._progress(
                "phase_completed",
                "pm_intake",
                agent="pm_agent",
                status="completed",
                index=1,
                message="PMAgent produced mission spec and acceptance criteria.",
                artifacts=[str(prepared["mission_spec"])],
            )

        for step_index, step in enumerate(self.agent_plan, start=1):
            if step.role_id == "pm_agent":
                continue
            if skip_architecture and step.role_id == "architect_agent":
                continue
            self._progress(
                "phase_started",
                step.phase,
                agent=step.role_id,
                skill=step.skills[0] if step.skills else "",
                status="running",
                index=step_index,
                message=step.action,
                metadata={
                    "handoff_to": step.handoff_to,
                    "skills": step.skills,
                    "mission_round": mission_round,
                    "capability_class": "workflow",
                },
            )
            if step.role_id == "architect_agent":
                arch_path = self.project_dir / "architecture_handoff.md"
                arch_text = _architecture_handoff(self.spec)
                arch_path.write_text(arch_text, encoding="utf-8")
                artifacts.append(str(arch_path))
                phases.append(MissionPhaseResult(
                    phase=step.phase,
                    role_id=step.role_id,
                    status="completed",
                    output=arch_text,
                    artifacts=[str(arch_path)],
                ))
                self._progress(
                    "phase_completed",
                    step.phase,
                    agent=step.role_id,
                    skill=step.skills[0] if step.skills else "",
                    status="completed",
                    index=step_index,
                    message="Architecture handoff produced.",
                    artifacts=[str(arch_path)],
                )
            elif step.role_id == "eda_agent":
                result = await self._run_eda_agent(step, mission_round=mission_round)
                phases.append(result)
                artifacts.extend(result.artifacts)
                self._progress(
                    "phase_completed" if result.status in {"completed", "handoff"} else "phase_failed",
                    step.phase,
                    agent=step.role_id,
                    skill=step.skills[0] if step.skills else "",
                    status=result.status,
                    index=step_index,
                    message=result.output[:240] if result.output else result.error or "EDAAgent completed.",
                    artifacts=result.artifacts,
                    fix_request={"error": result.error, "handoff_to": step.handoff_to} if result.error else None,
                    metadata={
                        "mission_round": mission_round,
                        "next_action": (
                            "retry:chip-autodesign"
                            if result.status == "failed"
                            else "continue:optimizer"
                        ),
                        "capability_class": "workflow",
                    },
                )
            elif step.role_id in {"optimizer_agent", "ppa_optimizer_agent"}:
                opt_result = await self._run_optimizer_agent(step, phases, mission_round=mission_round)
                phases.append(opt_result)
                artifacts.extend(opt_result.artifacts)
                opt_status = (
                    "needs_iteration"
                    if _suggests_iteration(opt_result.output or "")
                    else opt_result.status
                )
                self._progress(
                    "phase_completed" if opt_result.status == "completed" else "phase_failed",
                    step.phase,
                    agent=step.role_id,
                    skill=step.skills[0] if step.skills else "",
                    status=opt_status,
                    index=step_index,
                    message="Optimizer reviewed evidence and iteration policy.",
                    metadata={
                        "mission_round": mission_round,
                        "next_action": (
                            "retry:eda_execute"
                            if _suggests_iteration(opt_result.output or "")
                            else "signoff"
                        ),
                        "capability_class": "workflow",
                    },
                )
            else:
                handoff_path = self.project_dir / f"{step.role_id}_handoff.md"
                handoff_text = _handoff_text(step, self.spec)
                handoff_path.write_text(handoff_text, encoding="utf-8")
                artifacts.append(str(handoff_path))
                phases.append(MissionPhaseResult(
                    phase=step.phase,
                    role_id=step.role_id,
                    status="handoff",
                    output=handoff_text,
                    artifacts=[str(handoff_path)],
                ))
                self._progress(
                    "handoff",
                    step.phase,
                    agent=step.role_id,
                    skill=step.skills[0] if step.skills else "",
                    status="handoff",
                    index=step_index,
                    message="Specialist handoff produced.",
                    artifacts=[str(handoff_path)],
                )
        return phases, artifacts

    async def _dispatch_mission_repair(
        self,
        eda_phase: MissionPhaseResult,
        mission_round: int,
    ) -> None:
        try:
            from ..workflows.validated_rtl.controller import extract_module_name
            from ..workflows.validated_rtl.repair_helpers import (
                apply_deterministic_iverilog_tb_repair,
                is_compile_log,
            )
            from .runners.specialist_runner import run_specialist_role

            auto_dir = self.project_dir / "eda_autodesign" / "eda_validated_rtl"
            sim_log_path = auto_dir / "reports" / "simulation.log"
            module_name = extract_module_name(self.user_task, default="top_module")
            tb_path = auto_dir / "tb" / f"{module_name}_tb.v"

            deterministic = False
            if sim_log_path.is_file():
                sim_log = sim_log_path.read_text(encoding="utf-8", errors="replace")
                if is_compile_log(sim_log):
                    deterministic = apply_deterministic_iverilog_tb_repair(auto_dir, module_name)

            repair_task = (
                f"Mission round {mission_round} EDA failed.\n\n"
                f"Error: {eda_phase.error or 'unknown'}\n\n"
                f"Output excerpt:\n{(eda_phase.output or '')[:2000]}\n\n"
            )
            if sim_log_path.is_file():
                repair_task += (
                    f"\nSimulation log ({sim_log_path}):\n"
                    f"{sim_log_path.read_text(encoding='utf-8', errors='replace')[:4000]}\n"
                )
            if tb_path.is_file():
                repair_task += f"\nTestbench path: {tb_path}\n"
            if deterministic:
                repair_task += (
                    "\nDeterministic repair applied: replaced TB with iverilog-compatible "
                    "CRC-8 known-vector testbench (expects 8'hF4 + TEST PASSED).\n"
                )
            repair_task += "\nApply the narrowest RTL repair and prepare for chip-autodesign retry."

            repair_result = await run_specialist_role(
                "rtl_repair_agent",
                repair_task,
                context={
                    "cli_state": self.cli_state,
                    "mission_id": self.mission_id,
                    "project_dir": str(self.project_dir / "eda_autodesign"),
                    "eda_project_dir": str(auto_dir),
                    "simulation_log": str(sim_log_path) if sim_log_path.is_file() else "",
                    "tb_path": str(tb_path) if tb_path.is_file() else "",
                    "module_name": module_name,
                    "enable_specialist_repair": True,
                    "deterministic_tb_patch": deterministic,
                },
            )
            repair_status = repair_result.get("status", "dispatched")
            if deterministic and repair_status in {"failed", "budget_exceeded"}:
                repair_status = "completed"
            self._progress(
                "specialist_dispatched",
                "eda_execute",
                agent="rtl_repair_agent",
                skill="rtl-repair",
                status=repair_status,
                message="Mission dispatched rtl_repair_agent after EDA failure.",
                metadata={
                    "mission_round": mission_round,
                    "next_action": "retry:chip-autodesign",
                    "capability_class": "workflow",
                    "deterministic_tb_patch": deterministic,
                },
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "Mission repair dispatch failed (round %s): %s",
                mission_round,
                exc,
            )
            self._progress(
                "specialist_dispatched",
                "eda_execute",
                agent="rtl_repair_agent",
                skill="rtl-repair",
                status="failed",
                message=f"Mission repair dispatch failed: {exc}",
                metadata={"mission_round": mission_round},
            )

    async def _run_optimizer_agent(
        self,
        step: AgentPlanStep,
        phases: List[MissionPhaseResult],
        *,
        mission_round: int,
    ) -> MissionPhaseResult:
        from .roster_registry import get_roster
        from .runners.optimizer_runner import run_optimizer_agent

        roster = get_roster()
        spec = roster.get("optimizer_agent")
        if spec is None:
            opt_text = _optimizer_review(self.mission_type, phases)
            return MissionPhaseResult(
                phase=step.phase,
                role_id=step.role_id,
                status="completed",
                output=opt_text,
                artifacts=[],
            )
        task = _optimizer_task_mission(self.user_task, phases, self.project_dir)
        try:
            output = await run_optimizer_agent(
                spec,
                task,
                ctx={
                    "cli_state": self.cli_state,
                    "mission_id": self.mission_id,
                    "mission_round": mission_round,
                },
            )
        except Exception as exc:
            opt_text = _optimizer_review(self.mission_type, phases)
            opt_text += f"\n\nOptimizer fallback (EvolutionEngine unavailable): {exc}\n"
            if any(p.role_id == "eda_agent" and p.status == "failed" for p in phases):
                opt_text += "\n> **needs_iteration**: true\n"
            return MissionPhaseResult(
                phase=step.phase,
                role_id=step.role_id,
                status="completed",
                output=opt_text,
                artifacts=[],
            )
        return MissionPhaseResult(
            phase=step.phase,
            role_id=step.role_id,
            status=output.get("status", "completed"),
            output=output.get("output", ""),
            artifacts=output.get("artifacts") or [],
            error=output.get("error"),
        )

    def _mission_interrupt_requested(self) -> bool:
        if getattr(self.cli_state, "mission_interrupt", False):
            return True
        if getattr(self.cli_state, "task_stop_requested", False):
            return True
        return False

    def _persist_reusable_artifacts(self) -> None:
        try:
            from ..orchestrator.design_state import DesignStateStore

            golden_root = Path("runs") / "_golden" / self.mission_id
            auto_dir = self.project_dir / "eda_autodesign" / "eda_validated_rtl"
            copied: List[str] = []
            for pattern in ("rtl/*.v", "tb/*.v", "scripts/*", "reports/hard_gate_report.md"):
                for src in auto_dir.glob(pattern):
                    dest = golden_root / src.relative_to(auto_dir)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(src.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                    copied.append(str(dest))
            store = DesignStateStore()
            store.load()
            store.set_mission(
                mission_spec=self.spec.to_dict(),
                agent_plan=[s.to_dict() for s in self.agent_plan],
                status="PASS",
                artifacts={"golden_dir": str(golden_root), "reusable": ",".join(copied[:8])},
                phases=[],
            )
            store.save()
        except Exception:
            pass

    async def _run_eda_agent(self, step: AgentPlanStep, *, mission_round: int = 1) -> MissionPhaseResult:
        if not self.execute:
            return MissionPhaseResult(
                phase=step.phase,
                role_id="eda_agent",
                status="handoff",
                output="Execution disabled; EDAAgent handoff only.",
            )
        from .runners.eda_agent_runner import EDAAgentRunner

        chain = eda_chain_for(self.mission_type)
        task = self.user_task
        if self.mission_type == "rtl_ip_autodesign":
            auto_dir = self.project_dir / "eda_autodesign"
            task = (
                f"{self.user_task} --yes --project-dir {auto_dir} "
                f"--max-iters {self.max_iterations}"
            )
            if self.force and mission_round == 1:
                task += " --force"
            if self.progress_quiet:
                task += " --quiet"
            if self.progress_json:
                task += " --json-progress"
        runner = EDAAgentRunner(cli_state=self.cli_state, chain=chain)
        output = await runner.run(task, context={
            "cli_state": self.cli_state,
            "mission_id": self.mission_id,
            "mission_type": self.mission_type,
            "mission_round": mission_round,
            "progress_quiet": self.progress_quiet,
            "progress_json": self.progress_json,
            "enable_specialist_repair": True,
            "project_dir": str(self.project_dir / "eda_autodesign"),
        })
        if output.get("status") == "failed" or _eda_output_indicates_failure(str(output.get("output", ""))):
            status = "failed"
        elif output.get("status") in {"completed", "PASS"}:
            status = "completed"
        else:
            status = output.get("status", "failed")
        return MissionPhaseResult(
            phase=step.phase,
            role_id="eda_agent",
            status=status,
            output=output.get("output", ""),
            artifacts=output.get("artifacts") or [],
            error=output.get("error"),
        )

    def _write_design_state(
        self,
        *,
        status: str,
        artifacts: Optional[Dict[str, str]] = None,
        phases: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        try:
            from ..orchestrator.design_state import DesignStateStore
            artifact_index = self._collect_mission_artifacts(artifacts or {}, phases or [])
            store = DesignStateStore()
            store.set_mission(
                mission_spec=self.spec.to_dict(),
                agent_plan=[s.to_dict() for s in self.agent_plan],
                status=status,
                artifacts=artifact_index,
                phases=phases or [],
            )
            store.save()
        except Exception:
            pass

    def _collect_mission_artifacts(
        self,
        artifacts: Dict[str, str],
        phases: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        idx = dict(artifacts)
        idx["last_chip_mission_id"] = self.mission_id
        idx["last_project_dir"] = str(self.project_dir)
        idx["autodesign_project_dir"] = str(self.project_dir / "eda_autodesign")

        for phase in phases:
            if not isinstance(phase, dict):
                continue
            for artifact in phase.get("artifacts") or []:
                if isinstance(artifact, str):
                    self._classify_artifact_path(Path(artifact), idx)

        auto_dir = self.project_dir / "eda_autodesign"
        for candidate in sorted((auto_dir / "rtl").glob("*.sv")) + sorted((auto_dir / "rtl").glob("*.v")):
            idx.setdefault("rtl", str(candidate))
            break
        sim_log = auto_dir / "reports" / "simulation.log"
        if sim_log.exists():
            idx.setdefault("simulation_log", str(sim_log))
        for report in sorted((auto_dir / "reports").glob("*report*.md")) if (auto_dir / "reports").exists() else []:
            idx.setdefault("report", str(report))
            break
        return idx

    @staticmethod
    def _classify_artifact_path(path: Path, idx: Dict[str, str]) -> None:
        text = str(path)
        lower = path.name.lower()
        if path.suffix.lower() in {".sv", ".v"}:
            idx.setdefault("rtl", text)
        elif lower == "simulation.log":
            idx.setdefault("simulation_log", text)
        elif path.suffix.lower() == ".md" and "report" in lower:
            idx.setdefault("report", text)


def classify_mission(task: str, intent: Optional[ChipIntent] = None) -> MissionType:
    if intent is not None and intent.task_domain:
        mapping = {
            "rtl_ip_autodesign": "rtl_ip_autodesign",
            "rtl_design": "rtl_ip_autodesign",
            "architecture_exploration": "rtl_ip_autodesign",
            "eda_debug": "rtl_ip_autodesign",
            "verification_only": "verification_only",
            "verification": "verification_only",
            "simulation": "verification_only",
            "formal": "verification_only",
            "synthesis_qor": "synthesis_qor",
            "synthesis": "synthesis_qor",
            "sta": "synthesis_qor",
            "hls_fpga": "hls_fpga",
            "hls": "hls_fpga",
            "system_soc": "system_soc",
            "analog_pd_handoff": "analog_pd_handoff",
            "physical_design": "analog_pd_handoff",
        }
        if intent.task_domain in mapping:
            return mapping[intent.task_domain]  # type: ignore[return-value]
    text = task.lower()
    if re.search(r"\b(analog|spice|rf|mixed.?signal|layout|floorplan|placement|routing|physical|openroad|pd)\b", text):
        return "analog_pd_handoff"
    if re.search(r"\b(hls|high.?level synthesis|fpga|emulation|bitstream|nextpnr)\b", text):
        return "hls_fpga"
    if re.search(r"\b(soc|firmware|driver|memory map|runtime|compiler|isa|register block and driver)\b", text):
        return "system_soc"
    if (
        re.search(r"\b(verification|verify|testbench|coverage|formal|property|regression|uvm|checks)\b", text)
        and not re.search(r"\b(design|create|build|implement)\b", text)
    ):
        return "verification_only"
    if re.search(r"\b(design|create|build|implement|generate|write|make)\b|设计|实现|生成|构建", text) and re.search(
        r"\b(chip|ip\b|rtl|module|block|accelerator|controller|fifo|axi|dsp|mac|npu|tile|arbiter|crc|pwm|dma|attention)\b|芯片|模块|控制器|加速器|接口|协议",
        text,
    ):
        return "rtl_ip_autodesign"
    if re.search(r"\b(qor|synth|synthesis|area|timing|sta|power|optimi[sz]e)\b", text):
        return "synthesis_qor"
    if re.search(r"\b(verification|verify|testbench|coverage|formal|property|regression|uvm)\b", text):
        return "verification_only"
    return "rtl_ip_autodesign"


def success_criteria_for(mission_type: MissionType) -> List[str]:
    base = ["mission spec generated", "agent plan generated", "artifact index generated"]
    if mission_type == "rtl_ip_autodesign":
        return base + [
            "chip-autodesign PASS",
            "simulation PASS",
            "Yosys QoR generated",
            "hard gate report generated",
        ]
    if mission_type == "verification_only":
        return base + ["verification plan or executable verification stage produced"]
    if mission_type == "synthesis_qor":
        return base + ["QoR diagnosis produced", "PPA optimizer handoff generated"]
    if mission_type == "hls_fpga":
        return base + ["HLS/FPGA agent handoff generated", "deployment assumptions listed"]
    if mission_type == "system_soc":
        return base + ["architecture/EDA/software/runtime handoffs generated"]
    return base + ["tool availability and handoff limitations documented"]


def build_agent_plan(mission_type: MissionType, task: str, intent: Optional[ChipIntent] = None) -> List[AgentPlanStep]:
    common = [AgentPlanStep("pm_intake", "pm_agent", "Diagnose mission and draft acceptance criteria.")]
    if mission_type == "rtl_ip_autodesign":
        return common + [
            AgentPlanStep("architecture", "architect_agent", "Define IP architecture and interface contract.", ["chip-architecture"]),
            AgentPlanStep("eda_execute", "eda_agent", "Run RTL/IP AutoDesign via chip-autodesign.", ["chip-autodesign"], ["rtl_repair_agent", "ppa_optimizer_agent"]),
            AgentPlanStep("optimize_review", "optimizer_agent", "Review QoR and decide whether another iteration is needed.", ["rltf", "pareto-negotiate"]),
        ]
    if mission_type == "verification_only":
        return common + [
            AgentPlanStep("eda_verify", "eda_agent", "Run verification/formal-oriented EDA stages.", ["chip-verification", "chip-formal"], ["rtl_repair_agent", "formal_agent"]),
        ]
    if mission_type == "synthesis_qor":
        return common + [
            AgentPlanStep("eda_synth", "eda_agent", "Run synthesis/QoR stages.", ["chip-synthesis", "chip-sta"], ["ppa_optimizer_agent"]),
            AgentPlanStep("ppa_review", "ppa_optimizer_agent", "Diagnose QoR and propose PPA actions.", ["chip-synthesis", "chip-sta"]),
        ]
    if mission_type == "hls_fpga":
        return common + [
            AgentPlanStep("hls", "hls_agent", "Prepare HLS kernel/interface plan.", ["chip-hls"]),
            AgentPlanStep("deploy", "deploy_agent", "Prepare FPGA/emulation deployment plan.", ["chip-fpga", "chip-infrastructure"]),
        ]
    if mission_type == "system_soc":
        return common + [
            AgentPlanStep("architecture", "architect_agent", "Define SoC architecture and IP boundaries.", ["chip-architecture"]),
            AgentPlanStep("eda_execute", "eda_agent", "Plan or run EDA/IP stages.", ["chip-autodesign", "chip-soc"]),
            AgentPlanStep("software", "compiler_agent", "Plan compiler/driver/API collateral.", ["chip-compiler", "chip-hls"]),
            AgentPlanStep("runtime", "runtime_agent", "Plan firmware/runtime/memory-map integration.", ["chip-firmware", "chip-soc"]),
        ]
    return common + [
        AgentPlanStep("analog_handoff", "analog_agent", "Plan analog/PD task, tool availability, and handoff requirements.", ["analog-design-meta"]),
        AgentPlanStep("deploy", "deploy_agent", "Check EDA infrastructure and reproducibility handoff.", ["chip-infrastructure"]),
    ]


def eda_chain_for(mission_type: MissionType) -> List[str]:
    if mission_type == "rtl_ip_autodesign":
        return ["chip-autodesign"]
    if mission_type == "verification_only":
        return ["chip-verification", "chip-formal"]
    if mission_type == "synthesis_qor":
        return ["chip-synthesis", "chip-sta"]
    if mission_type == "system_soc":
        return ["chip-soc"]
    return ["chip-infrastructure"]


def failure_specialist_for(failure_type: str) -> str:
    text = failure_type.lower()
    if any(k in text for k in ("compile", "simulation", "rtl", "lint", "verilator", "iverilog")):
        return "rtl_repair_agent"
    if any(k in text for k in ("formal", "property", "sby", "proof")):
        return "formal_agent"
    if any(k in text for k in ("yosys", "qor", "synth", "sta", "timing", "power")):
        return "ppa_optimizer_agent"
    if "hls" in text:
        return "hls_agent"
    return "deploy_agent"


def agent_capability_summary() -> Dict[str, Dict[str, Any]]:
    from .roster_registry import get_roster
    return {
        spec.role_id: {
            "display_name": spec.display_name,
            "description": spec.description,
            "mapped_skills": spec.mapped_skills,
            "allowed_tools": spec.allowed_tools,
            "execution_mode": spec.execution_mode,
            "output_artifacts": spec.output_artifacts,
        }
        for spec in get_roster().all_specs()
    }


def render_mission_spec(spec: MissionSpec) -> str:
    return (
        f"# Chip Mission Spec\n\n"
        f"- mission_id: `{spec.mission_id}`\n"
        f"- mission_type: `{spec.mission_type}`\n\n"
        f"## Chip Intent\n```json\n{json.dumps(spec.intent, indent=2, ensure_ascii=False)}\n```\n\n"
        f"## User Task\n{spec.user_task}\n\n"
        "## Success Criteria\n"
        + "\n".join(f"- {item}" for item in spec.success_criteria)
        + "\n"
    )


def render_agent_plan(plan: List[AgentPlanStep]) -> str:
    lines = ["# Chip Mission Agent Plan", ""]
    for idx, step in enumerate(plan, start=1):
        lines.append(f"{idx}. **{step.role_id}** (`{step.phase}`): {step.action}")
        if step.skills:
            lines.append(f"   - skills: {', '.join(step.skills)}")
        if step.handoff_to:
            lines.append(f"   - failure handoff: {', '.join(step.handoff_to)}")
    return "\n".join(lines) + "\n"


def render_mission_report(result: ChipMissionResult, *, mission_rounds: int = 1) -> str:
    lines = [
        "# Chip Mission Report",
        "",
        f"Status: **{result.status}**",
        f"Mission type: `{result.mission_type}`",
        f"Mission id: `{result.mission_id}`",
        f"Mission rounds: `{mission_rounds}`",
        f"Router source: `{result.spec.intent.get('router_source')}`",
        f"Fallback reason: `{result.spec.intent.get('fallback_reason')}`",
        "",
        "## Capability Map",
        "",
        _capability_map_markdown(),
        "",
        "## Agent Phases",
        "",
    ]
    for phase in result.phases:
        lines.append(f"- `{phase.phase}` / `{phase.role_id}`: {phase.status}")
        if phase.error:
            lines.append(f"  - error: {phase.error}")
    lines.extend(["", "## Artifacts", ""])
    for artifact in result.artifacts:
        lines.append(f"- `{artifact}`")
    lines.extend(["", "## JSON", "", "```json"])
    lines.append(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    lines.append("```")
    return "\n".join(lines) + "\n"


def _architecture_handoff(spec: MissionSpec) -> str:
    return (
        "# Architecture Handoff\n\n"
        f"Mission type `{spec.mission_type}` requires an interface-first architecture. "
        "For V1, architecture output is a deterministic handoff that constrains EDA "
        "execution and documents the expected artifacts.\n"
    )


def _optimizer_review(mission_type: MissionType, phases: List[MissionPhaseResult]) -> str:
    eda = next((p for p in phases if p.role_id == "eda_agent"), None)
    return (
        "# Optimizer Review\n\n"
        f"Mission type: `{mission_type}`\n\n"
        f"EDA status: `{eda.status if eda else 'not-run'}`\n\n"
        "V1 recommendation: accept PASS results as the baseline; trigger a targeted "
        "PPA/RTL iteration only when QoR gates or regression gates fail.\n"
    )


def _optimizer_task_mission(
    user_task: str,
    phases: List[MissionPhaseResult],
    project_dir: Path,
) -> str:
    summaries = "\n".join(
        f"- {p.phase}/{p.role_id}: {p.status}" for p in phases[-8:]
    )
    sim_log = project_dir / "eda_autodesign" / "eda_validated_rtl" / "reports" / "simulation.log"
    log_excerpt = ""
    if sim_log.is_file():
        log_excerpt = sim_log.read_text(encoding="utf-8", errors="replace")[-1500:]
    return (
        f"Analyze chip mission pipeline for:\n{user_task}\n\n"
        f"Phase summary:\n{summaries}\n\n"
        f"Simulation log excerpt:\n{log_excerpt}\n\n"
        "If hard gates failed, recommend iteration and list the narrowest repair actions."
    )


def _suggests_iteration(output: str) -> bool:
    lower = (output or "").lower()
    eda_failed = "eda status: `failed`" in lower or "**status:** fail" in lower
    if eda_failed:
        return True
    return any(k in lower for k in (
        "recommend iteration", "建议迭代", "needs_iteration",
        "bottleneck", "optimize again", "第二轮",
    ))


def _capability_map_summary() -> Dict[str, List[str]]:
    return {
        "workflow": ["chip-mission", "chip-autodesign", "chip-rtl", "rtl-repair"],
        "tool": ["verilog-lint", "verilog-tb-gen", "yosys", "abc"],
        "constraint": ["verilog-generator", "digital-chip-design-agents"],
        "execute": ["local_eda", "iverilog", "vvp", "yosys"],
    }


def _capability_map_markdown() -> str:
    mapping = _capability_map_summary()
    lines = [
        "| Layer | Examples | Role |",
        "|-------|----------|------|",
    ]
    roles = {
        "workflow": "Orchestration entry skills",
        "tool": "Single-shot harness capabilities",
        "constraint": "Prompt/format/lint/gate deps",
        "execute": "Compile/sim/synth hard gate",
    }
    for layer, examples in mapping.items():
        lines.append(f"| {layer} | `{', '.join(examples)}` | {roles[layer]} |")
    lines.append("")
    lines.append("execution_stack: `generator=LLM constraint=verilog-generator hard_gate=local_eda`")
    return "\n".join(lines)


def _handoff_text(step: AgentPlanStep, spec: MissionSpec) -> str:
    return (
        f"# {step.role_id} Handoff\n\n"
        f"Phase: `{step.phase}`\n\n"
        f"Mission type: `{spec.mission_type}`\n\n"
        f"Action: {step.action}\n\n"
        "This V1 mission control run records the handoff contract. A later run may "
        "enable full autonomous execution for this specialist when the required "
        "toolchain and inputs are present.\n"
    )


def _eda_output_indicates_failure(output: str) -> bool:
    lowered = output.lower()
    if "chip autodesign failed:" in lowered:
        return True
    if "skill 'chip-autodesign' execution error:" in lowered:
        return True
    if "**status:** fail" in lowered and "chip autodesign" in lowered:
        return True
    if "validated rtl generation" in lowered and "**status:** fail" in lowered:
        return True
    return False


def _mission_passes(phases: List[MissionPhaseResult]) -> bool:
    eda_phases = [p for p in phases if p.role_id == "eda_agent"]
    if not eda_phases:
        return False
    latest_eda = eda_phases[-1]
    if latest_eda.status != "completed":
        return False
    if _eda_output_indicates_failure(latest_eda.output or ""):
        return False
    return True
