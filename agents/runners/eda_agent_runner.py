"""
EDAAgent meta-coordinator — sequential chip-* orchestrator chain.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default EDA pipeline (verification preferred over formal when both available)
DEFAULT_EDA_CHAIN: List[str] = [
    "chip-rtl",
    "chip-verification",
    "chip-synthesis",
    "chip-sta",
    "chip-pd",
]

# Skills that may be skipped on failure without aborting entire chain
OPTIONAL_SKILLS = frozenset({"chip-pd", "chip-formal"})

# Failure-to-specialist dispatch used when the enclosing multi-agent pipeline
# enables specialist repair.
FAILURE_SPECIALISTS = {
    "chip-rtl": "rtl_repair_agent",
    "chip-verification": "rtl_repair_agent",
    "chip-formal": "formal_agent",
    "chip-synthesis": "ppa_optimizer_agent",
    "chip-sta": "ppa_optimizer_agent",
    "chip-pd": "ppa_optimizer_agent",
}


class EDAAgentRunner:
    """Run EDA sub-pipeline by invoking chip-* skill executors in order."""

    def __init__(self, cli_state: Any = None, chain: Optional[List[str]] = None):
        self.cli_state = cli_state
        self.chain = chain or list(DEFAULT_EDA_CHAIN)

    async def run(
        self,
        task: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from ...capability_registry import get_capability_registry
        from ...orchestrator.design_state import DesignStateStore

        ctx = dict(context or {})
        if self.cli_state is not None:
            ctx.setdefault("cli_state", self.cli_state)

        store = DesignStateStore()
        store.load()
        store.update_multi_agent_phase("eda", agent_status={"eda_agent": "running"})
        store.save()

        cap = get_capability_registry()
        step_results: List[Dict[str, Any]] = []
        combined_output: List[str] = []
        failed = False
        last_error: Optional[str] = None

        for skill_name in self.chain:
            logger.info("EDAAgent: running %s", skill_name)
            step_task = f"{task}\n\n[EDA sub-stage: {skill_name}]"
            try:
                result = await cap.execute(skill_name, {"args": step_task}, ctx)
                text = _extract_text(result)
                step_results.append({
                    "skill": skill_name,
                    "status": "completed",
                    "output_preview": text[:500],
                })
                combined_output.append(f"## {skill_name}\n{text[:2000]}")
                store.merge_stage_qor(
                    "eda-agent", skill_name.replace("chip-", ""),
                    {"step": skill_name}, "PASS",
                )
            except Exception as e:
                last_error = str(e)
                step_results.append({
                    "skill": skill_name,
                    "status": "failed",
                    "error": last_error,
                })
                store.add_fix_request(
                    summary=f"EDA stage {skill_name} failed",
                    detail=last_error,
                    source_agent="eda_agent",
                )
                if ctx.get("enable_specialist_repair"):
                    repair_result = await self._run_failure_specialist(
                        skill_name, task, last_error, ctx
                    )
                    if repair_result is not None:
                        repair_agent = repair_result.get("role_id")
                        repair_status = repair_result.get("status")
                        repair_output = repair_result.get("output") or ""
                        step_results.append({
                            "skill": skill_name,
                            "status": "specialist_dispatched",
                            "agent": repair_agent,
                            "agent_status": repair_status,
                            "output_preview": repair_output[:500],
                        })
                        combined_output.append(
                            "## Specialist Dispatch\n"
                            f"SPECIALIST_DISPATCH stage={skill_name} "
                            f"agent={repair_agent} status={repair_status}\n\n"
                            f"{repair_output[:2000]}"
                        )
                if skill_name in OPTIONAL_SKILLS:
                    combined_output.append(f"## {skill_name}\n⚠️ Skipped optional stage: {last_error}")
                    continue
                failed = True
                break

        final_status = "failed" if failed else "completed"
        store.update_multi_agent_phase(
            "eda",
            agent_status={"eda_agent": final_status},
            artifacts_index={"eda_steps": str(len(step_results))},
        )
        store.save()

        return {
            "role_id": "eda_agent",
            "status": final_status,
            "output": "\n\n".join(combined_output),
            "artifacts": ["artifacts/eda/"],
            "error": last_error,
            "steps": step_results,
        }

    async def _run_failure_specialist(
        self,
        skill_name: str,
        task: str,
        error: str,
        ctx: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        role_id = FAILURE_SPECIALISTS.get(skill_name)
        if not role_id:
            return None
        from .specialist_runner import run_specialist_role

        specialist_task = (
            f"EDA stage failed: {skill_name}\n\n"
            f"Original task:\n{task}\n\n"
            f"Failure log:\n{error}\n\n"
            "Diagnose the failure and propose or apply the narrowest repair."
        )
        try:
            return await run_specialist_role(role_id, specialist_task, context=ctx)
        except Exception as exc:
            logger.warning("Failure specialist %s failed: %s", role_id, exc)
            return {
                "role_id": role_id,
                "status": "failed",
                "output": "",
                "artifacts": [],
                "error": str(exc),
            }


def _extract_text(result: Any) -> str:
    if isinstance(result, list):
        parts = []
        for item in result:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n\n".join(parts)
    return str(result) if result is not None else ""
