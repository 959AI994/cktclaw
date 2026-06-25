"""
OptimizerAgent runner — combines EvolutionEngine bottleneck analysis with worker LLM.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default PPA targets when design_state lacks explicit thresholds
_DEFAULT_TARGETS = {
    "area": 1.0,
    "delay": 1.0,
    "power": 1.0,
    "wns": 0.0,
    "tns": 0.0,
}


def _bottlenecks_from_design_state(data: dict) -> List:
    """Build Bottleneck list from orchestrator_qor and multi_agent phase statuses."""
    from ...loop.evolution import Bottleneck

    bottlenecks: List[Bottleneck] = []
    qor = data.get("orchestrator_qor") or {}
    for domain, metrics in qor.items():
        if not isinstance(metrics, dict):
            continue
        for metric_name, value in metrics.items():
            if not isinstance(value, (int, float)):
                continue
            target = _DEFAULT_TARGETS.get(metric_name, 1.0)
            gap = abs(value - target)
            relative_gap = gap / max(abs(target), 1e-6)
            severity = (
                "critical" if relative_gap > 0.5
                else "major" if relative_gap > 0.2
                else "minor"
            )
            bottlenecks.append(Bottleneck(
                task_id=f"{domain}:{metric_name}",
                domain=str(domain),
                metric_name=str(metric_name),
                current_value=float(value),
                target_value=float(target),
                severity=severity,
                description=f"{metric_name}={value} vs target {target}",
            ))

    ma = data.get("multi_agent") or {}
    agent_status = ma.get("agent_status") or {}
    for role_id, status in agent_status.items():
        if status in ("failed", "error"):
            bottlenecks.append(Bottleneck(
                task_id=role_id,
                domain=role_id.replace("_agent", ""),
                metric_name="phase_status",
                current_value=0.0,
                target_value=1.0,
                severity="critical",
                description=f"Agent phase {role_id} ended with status={status}",
            ))

    severity_order = {"critical": 0, "major": 1, "minor": 2}
    bottlenecks.sort(key=lambda b: severity_order.get(b.severity, 99))
    return bottlenecks


def _format_evolution_report(feedback: Dict[str, str], bottlenecks: List) -> str:
    lines = ["# Optimization Report (EvolutionEngine)", ""]
    if bottlenecks:
        lines.append("## Bottleneck Analysis")
        for bn in bottlenecks[:10]:
            lines.append(
                f"- [{bn.severity}] **{bn.domain}** / {bn.metric_name}: "
                f"{bn.current_value} → target {bn.target_value} — {bn.description}"
            )
        lines.append("")
    if feedback:
        lines.append("## Domain Feedback")
        for domain, text in feedback.items():
            lines.append(f"### {domain}")
            lines.append(text)
            lines.append("")
    else:
        lines.append("No critical bottlenecks detected from design_state QoR.")
    return "\n".join(lines)


async def run_optimizer_agent(
    spec,
    task: str,
    ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run OptimizerAgent: EvolutionEngine analysis + optional worker LLM narrative.
    """
    from ...loop.evolution import EvolutionEngine
    from ...orchestrator.design_state import DesignStateStore

    store = DesignStateStore()
    data = store.load()
    bottlenecks = _bottlenecks_from_design_state(data)

    engine = EvolutionEngine()
    feedback = await engine.feedback_generator.generate_feedback(
        bottlenecks, engine.experience_store.get_all(),
    )
    evolution_md = _format_evolution_report(feedback, bottlenecks)

    report_path = Path("artifacts/optimization/report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(evolution_md, encoding="utf-8")

    enriched_task = (
        f"{task}\n\n## EvolutionEngine Pre-analysis\n{evolution_md[:4000]}\n\n"
        "Expand into a prioritized optimization plan. "
        "If iteration is needed, include 'recommend iteration' in the report."
    )
    from .specialist_runner import _run_worker
    worker_result = await _run_worker(spec, enriched_task, ctx)

    combined = f"{evolution_md}\n\n---\n\n## Agent Analysis\n{worker_result.get('output', '')}"
    report_path.write_text(combined, encoding="utf-8")

    needs_iteration = any(
        k in combined.lower()
        for k in ("recommend iteration", "建议迭代", "needs_iteration", "第二轮")
    )
    if needs_iteration:
        combined += "\n\n> **needs_iteration**: true"

    status = worker_result.get("status", "completed")
    artifacts = list(spec.output_artifacts or [])
    if str(report_path) not in artifacts:
        artifacts.append(str(report_path))

    return {
        "role_id": spec.role_id,
        "status": status,
        "output": combined,
        "artifacts": artifacts,
        "error": worker_result.get("error"),
        "agent_id": worker_result.get("agent_id"),
        "evolution_feedback": feedback,
    }
