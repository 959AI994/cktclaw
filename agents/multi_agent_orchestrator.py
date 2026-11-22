"""
MultiAgentOrchestrator — seven-agent full-stack pipeline for /chip-system.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

PipelineMode = Literal["full", "eda_only", "custom"]

PHASE_ORDER_FULL = [
    ("pm", "pm_agent"),
    ("arch", "architect_agent"),
    ("eda", "eda_agent"),
    ("parallel_sw", None),  # compiler + runtime parallel
    ("deploy", "deploy_agent"),
    ("optimize", "optimizer_agent"),
]


@dataclass
class PhaseResult:
    phase: str
    role_id: str
    status: str
    output: str = ""
    error: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)


@dataclass
class MultiAgentResult:
    session_id: str
    goal: str
    status: str
    phases: List[PhaseResult] = field(default_factory=list)
    spec_markdown: str = ""
    optimization_rounds: int = 0
    needs_iteration: bool = False

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "status": self.status,
            "spec_markdown": self.spec_markdown,
            "optimization_rounds": self.optimization_rounds,
            "needs_iteration": self.needs_iteration,
            "phases": [
                {
                    "phase": p.phase,
                    "role_id": p.role_id,
                    "status": p.status,
                    "output_preview": p.output[:500],
                    "error": p.error,
                    "artifacts": p.artifacts,
                }
                for p in self.phases
            ],
        }


_FULL_PHASE_TOTAL = 7
_EDA_ONLY_PHASE_TOTAL = 2


class MultiAgentOrchestrator:
    """Run PMAgent → Architect → EDA → (Compiler∥Runtime) → Deploy → Optimizer."""

    def __init__(
        self,
        cli_state: Any = None,
        *,
        max_optimization_rounds: int = 2,
    ):
        self.cli_state = cli_state
        self.max_optimization_rounds = max_optimization_rounds
        self._phase_total = _FULL_PHASE_TOTAL
        self._phase_index = 0

    def _report_phase(self, phase: str, role_id: str) -> None:
        """Emit WebConsole progress when running from Web orchestrator."""
        self._phase_index += 1
        console = getattr(self.cli_state, "console", None) if self.cli_state else None
        if console is None:
            return
        label = f"{role_id} ({phase})"
        if hasattr(console, "emit_stage"):
            console.emit_stage(label, self._phase_index, self._phase_total)
        try:
            from ..runtime.chip_progress import publish_chip_progress
            publish_chip_progress(
                event_type="phase_started",
                cli_state=self.cli_state,
                phase=phase,
                agent=role_id,
                skill="chip-system",
                status="running",
                index=self._phase_index,
                total=self._phase_total,
                message=label,
            )
        except Exception:
            pass
        if hasattr(console, "print"):
            console.print(f"[chip-system] Phase {self._phase_index}/{self._phase_total}: {label}")

    def _log_phase_status(self, phase: str, role_id: str, status: str) -> None:
        console = getattr(self.cli_state, "console", None) if self.cli_state else None
        if console and hasattr(console, "print"):
            console.print(f"[chip-system] {role_id} ({phase}): {status}")

    async def run(
        self,
        user_task: str,
        *,
        mode: PipelineMode = "full",
    ) -> MultiAgentResult:
        from ..orchestrator.design_state import DesignStateStore
        from .runners.specialist_runner import run_specialist_role

        session_id = uuid.uuid4().hex[:12]
        self._phase_index = 0
        self._phase_total = _EDA_ONLY_PHASE_TOTAL if mode == "eda_only" else _FULL_PHASE_TOTAL
        store = DesignStateStore()
        store.load()
        store.update_multi_agent_phase("pm", session_id=session_id)
        store.save()

        ctx = self._build_context(store)
        phases: List[PhaseResult] = []
        spec_md = ""

        # Phase 0 — PMAgent: generate spec (worker/coordinator prompt)
        self._report_phase("pm", "pm_agent")
        pm_result = await run_specialist_role("pm_agent", user_task, context=ctx)
        self._log_phase_status("pm", "pm_agent", pm_result.get("status", "?"))
        spec_md = pm_result.get("output") or _default_spec(user_task)
        store.set_spec(spec_md)
        store.update_multi_agent_phase("pm", agent_status={"pm_agent": pm_result.get("status", "?")})
        store.save()
        phases.append(_phase_from_result("pm", "pm_agent", pm_result))

        if mode == "eda_only":
            self._report_phase("eda", "eda_agent")
            eda_result = await run_specialist_role("eda_agent", user_task, context=ctx)
            self._log_phase_status("eda", "eda_agent", eda_result.get("status", "?"))
            phases.append(_phase_from_result("eda", "eda_agent", eda_result))
            return MultiAgentResult(
                session_id=session_id,
                goal=user_task,
                status=eda_result.get("status", "completed"),
                phases=phases,
                spec_markdown=spec_md,
            )

        # Phase 1 — Architect
        arch_task = f"{user_task}\n\n## Spec\n{spec_md[:3000]}"
        self._report_phase("arch", "architect_agent")
        arch_result = await run_specialist_role("architect_agent", arch_task, context=ctx)
        self._log_phase_status("arch", "architect_agent", arch_result.get("status", "?"))
        if arch_result.get("output"):
            store.set_arch(arch_result["output"])
        store.update_multi_agent_phase("arch", agent_status={"architect_agent": arch_result.get("status", "?")})
        store.save()
        phases.append(_phase_from_result("arch", "architect_agent", arch_result))

        # Phase 2 — EDA meta
        eda_task = f"{user_task}\n\nArchitecture context:\n{arch_result.get('output', '')[:2000]}"
        self._report_phase("eda", "eda_agent")
        eda_result = await run_specialist_role("eda_agent", eda_task, context=ctx)
        self._log_phase_status("eda", "eda_agent", eda_result.get("status", "?"))
        phases.append(_phase_from_result("eda", "eda_agent", eda_result))

        # Phase 3 — Compiler ∥ Runtime
        import asyncio
        self._report_phase("parallel_sw", "compiler_agent+runtime_agent")
        sw_ctx = {**ctx, "design_state_summary": store.summary_for_prompt()}
        compiler_coro = run_specialist_role(
            "compiler_agent",
            f"Build software stack for:\n{user_task}",
            context=sw_ctx,
        )
        runtime_coro = run_specialist_role(
            "runtime_agent",
            f"Design runtime/scheduler for:\n{user_task}",
            context=sw_ctx,
        )
        comp_result, rt_result = await asyncio.gather(compiler_coro, runtime_coro)
        self._log_phase_status("parallel_sw", "compiler_agent+runtime_agent", "completed")
        phases.append(_phase_from_result("compiler", "compiler_agent", comp_result))
        phases.append(_phase_from_result("runtime", "runtime_agent", rt_result))
        store.update_multi_agent_phase(
            "parallel_sw",
            agent_status={
                "compiler_agent": comp_result.get("status", "?"),
                "runtime_agent": rt_result.get("status", "?"),
            },
        )
        store.save()

        # Phase 4 — Deploy
        self._report_phase("deploy", "deploy_agent")
        deploy_result = await run_specialist_role(
            "deploy_agent",
            f"Deploy plan for:\n{user_task}\n\nCompiler: {comp_result.get('output', '')[:800]}",
            context=ctx,
        )
        self._log_phase_status("deploy", "deploy_agent", deploy_result.get("status", "?"))
        phases.append(_phase_from_result("deploy", "deploy_agent", deploy_result))

        # Phase 5 — Optimizer (+ optional iteration)
        opt_round = 0
        needs_iteration = False
        final_status = "completed"
        while opt_round <= self.max_optimization_rounds:
            self._report_phase(f"optimize_{opt_round}", "optimizer_agent")
            opt_result = await run_specialist_role(
                "optimizer_agent",
                _optimizer_task(user_task, phases, store),
                context=ctx,
            )
            self._log_phase_status(f"optimize_{opt_round}", "optimizer_agent", opt_result.get("status", "?"))
            phases.append(_phase_from_result(
                f"optimize_{opt_round}", "optimizer_agent", opt_result,
            ))
            needs_iteration = _suggests_iteration(opt_result.get("output", ""))
            if not needs_iteration or opt_round >= self.max_optimization_rounds:
                if opt_result.get("status") == "failed":
                    final_status = "completed_with_warnings"
                break
            opt_round += 1
            store.update_multi_agent_phase(
                "optimize",
                optimization_round=opt_round,
            )
            store.save()
            # Targeted re-run EDA on iteration
            eda_retry = await run_specialist_role(
                "eda_agent",
                f"Apply optimizations (round {opt_round}):\n{opt_result.get('output', '')[:1500]}",
                context=ctx,
            )
            phases.append(_phase_from_result(f"eda_retry_{opt_round}", "eda_agent", eda_retry))

        store.update_multi_agent_phase("done", agent_status={"pipeline": final_status})
        store.save()

        if any(p.status == "failed" for p in phases if p.phase in ("eda", "arch")):
            final_status = "failed"

        return MultiAgentResult(
            session_id=session_id,
            goal=user_task,
            status=final_status,
            phases=phases,
            spec_markdown=spec_md,
            optimization_rounds=opt_round,
            needs_iteration=needs_iteration,
        )

    def _build_context(self, store) -> Dict[str, Any]:
        return {
            "cli_state": self.cli_state,
            "design_state_summary": store.summary_for_prompt(),
        }


def _phase_from_result(phase: str, role_id: str, result: dict) -> PhaseResult:
    return PhaseResult(
        phase=phase,
        role_id=role_id,
        status=result.get("status", "unknown"),
        output=result.get("output", ""),
        error=result.get("error"),
        artifacts=result.get("artifacts") or [],
    )


def _default_spec(task: str) -> str:
    return (
        f"# System Specification\n\n"
        f"## Project Background\n{task}\n\n"
        f"## PPA Goals\n- TBD\n\n"
        f"## Constraints\n- TBD\n\n"
        f"## Milestones\n1. Architecture 2. EDA 3. Software 4. Deploy\n"
    )


def _optimizer_task(task: str, phases: List[PhaseResult], store) -> str:
    summaries = "\n".join(
        f"- {p.role_id}: {p.status}" for p in phases[-6:]
    )
    return (
        f"Analyze full pipeline for: {task}\n\n"
        f"Phase summary:\n{summaries}\n\n"
        f"Design state:\n{store.summary_for_prompt()}\n\n"
        f"Produce optimization report with prioritized recommendations."
    )


def _suggests_iteration(output: str) -> bool:
    lower = (output or "").lower()
    return any(k in lower for k in (
        "recommend iteration", "建议迭代", "needs_iteration",
        "bottleneck", "optimize again", "第二轮",
    ))
