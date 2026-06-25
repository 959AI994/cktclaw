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
