"""
Run a roster role by execution_mode — worker, orchestrator_direct, orchestrator_meta.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def run_specialist_role(
    role_id: str,
    task: str,
    *,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a specialist role from the agent roster.

    Returns:
        {"role_id", "status", "output", "artifacts", "error"}
    """
    from ..roster_registry import get_roster

    ctx = context or {}
    spec = get_roster().get(role_id)
    if spec is None:
        return {
            "role_id": role_id,
            "status": "failed",
            "output": "",
            "artifacts": [],
            "error": f"Unknown role: {role_id}",
        }

    if spec.execution_mode == "orchestrator_meta" and role_id == "eda_agent":
        from .eda_agent_runner import EDAAgentRunner
        runner = EDAAgentRunner(cli_state=ctx.get("cli_state"))
        return await runner.run(task, context=ctx)

    if role_id == "optimizer_agent":
        from .optimizer_runner import run_optimizer_agent
        return await run_optimizer_agent(spec, task, ctx)

    if spec.execution_mode in ("orchestrator_direct", "orchestrator_meta"):
        return await _run_via_skills(spec, task, ctx)

    return await _run_worker(spec, task, ctx)


async def _run_via_skills(spec, task: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke mapped chip-* skills sequentially; merge outputs."""
    from ...capability_registry import get_capability_registry

    cap = get_capability_registry()
    outputs: List[str] = []
    artifacts: List[str] = []
    primary_skill = spec.mapped_skills[0] if spec.mapped_skills else None

    if not primary_skill:
        return await _run_worker(spec, task, ctx)

    skill_ctx = {"cli_state": ctx.get("cli_state"), **ctx}
    try:
        result = await cap.execute(primary_skill, {"args": task}, skill_ctx)
        text = _result_to_text(result)
        outputs.append(text)
        if spec.output_artifacts:
            artifacts.extend(spec.output_artifacts)
        return {
            "role_id": spec.role_id,
            "status": "completed",
            "output": "\n\n".join(outputs),
            "artifacts": artifacts,
            "error": None,
            "skill": primary_skill,
        }
    except Exception as e:
        logger.error("Skill %s failed for %s: %s", primary_skill, spec.role_id, e)
        return {
            "role_id": spec.role_id,
            "status": "failed",
            "output": "",
            "artifacts": [],
            "error": str(e),
            "skill": primary_skill,
        }


async def _run_worker(spec, task: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    from ..runtime import get_agent_runtime

    runtime = get_agent_runtime()
    prompt = spec.system_prompt
    if ctx.get("design_state_summary"):
        prompt = f"{prompt}\n\n## Shared Context\n{ctx['design_state_summary']}"

    agent_id = await runtime.spawn_worker(
        name=spec.display_name,
        task=task,
        system_prompt=prompt,
        allowed_tools=spec.allowed_tools or None,
        model="deepseek" if spec.model_tier == "specialist" else "deepseek",
    )
    result = await runtime.wait_for(agent_id, timeout=600)
    status_info = runtime.get_status(agent_id) or {}
    st = status_info.get("status", "failed")
    return {
        "role_id": spec.role_id,
        "status": "completed" if st == "completed" else st,
        "output": result or "",
        "artifacts": list(spec.output_artifacts),
        "error": status_info.get("error"),
        "agent_id": agent_id,
    }


def _result_to_text(result: Any) -> str:
    if isinstance(result, list):
        parts = []
        for item in result:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n\n".join(parts)
    return str(result) if result is not None else ""
