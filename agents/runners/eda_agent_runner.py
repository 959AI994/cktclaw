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
    "chip-autodesign": "rtl_repair_agent",
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
        from ...runtime.chip_progress import publish_chip_progress

        ctx = dict(context or {})
        if self.cli_state is not None:
            ctx.setdefault("cli_state", self.cli_state)
        progress_cli_state = ctx.get("cli_state") or self.cli_state
        mission_id = str(ctx.get("mission_id") or "")
        quiet = bool(ctx.get("progress_quiet"))
        json_progress = bool(ctx.get("progress_json"))

        store = DesignStateStore()
        store.load()
        store.update_multi_agent_phase("eda", agent_status={"eda_agent": "running"})
        store.save()

        cap = get_capability_registry()
        step_results: List[Dict[str, Any]] = []
        combined_output: List[str] = []
        failed = False
        last_error: Optional[str] = None

        for step_index, skill_name in enumerate(self.chain, start=1):
            logger.info("EDAAgent: running %s", skill_name)
            step_task = f"{task}\n\n[EDA sub-stage: {skill_name}]"
            if skill_name == "chip-verification" and not _verification_target_available(step_task, ctx):
                last_error = "请提供 DUT RTL 路径，或选择上一轮 mission 的 RTL artifact。"
                step_results.append({
                    "skill": skill_name,
                    "status": "clarification",
                    "error": last_error,
                })
                combined_output.append(f"## {skill_name}\n{last_error}")
                store.add_fix_request(
                    summary="Verification target missing",
                    detail=last_error,
                    source_agent="eda_agent",
                )
                publish_chip_progress(
                    event_type="skill_failed",
                    cli_state=progress_cli_state,
                    mission_id=mission_id,
                    phase=skill_name.replace("chip-", ""),
                    agent="eda_agent",
                    skill=skill_name,
                    status="failed",
                    index=step_index,
                    total=len(self.chain),
                    message=last_error,
                    quiet=quiet,
                    json_progress=json_progress,
                )
                failed = True
                break
            publish_chip_progress(
                event_type="skill_started",
                cli_state=progress_cli_state,
                mission_id=mission_id,
                phase=skill_name.replace("chip-", ""),
                agent="eda_agent",
                skill=skill_name,
                status="running",
                index=step_index,
                total=len(self.chain),
                message=f"EDAAgent invoking {skill_name}.",
                quiet=quiet,
                json_progress=json_progress,
            )
            try:
                entry = await cap.get(skill_name)
                if entry is None or entry.skill_obj is None or not callable(getattr(entry.skill_obj, "executor", None)):
                    raise RuntimeError(f"Skill '{skill_name}' is not executable.")
                raw_result = await entry.skill_obj.executor(step_task, ctx)
                text = _extract_text(raw_result)
                if _skill_execution_failed(raw_result, text):
                    last_error = _failure_message(raw_result, text)
                    step_results.append({
                        "skill": skill_name,
                        "status": "failed",
                        "error": last_error,
                        "output_preview": text[:500],
                    })
                    combined_output.append(f"## {skill_name}\n{text[:2000]}")
                    store.add_fix_request(
                        summary=f"EDA stage {skill_name} failed",
                        detail=last_error,
                        source_agent="eda_agent",
                    )
                    publish_chip_progress(
                        event_type="skill_failed",
                        cli_state=progress_cli_state,
                        mission_id=mission_id,
                        phase=skill_name.replace("chip-", ""),
                        agent="eda_agent",
                        skill=skill_name,
                        status="failed",
                        index=step_index,
                        total=len(self.chain),
                        message=last_error[:500],
                        fix_request={
                            "failure_type": skill_name,
                            "log_excerpt": last_error[:1200],
                            "target_agent": FAILURE_SPECIALISTS.get(skill_name, ""),
                        },
                        quiet=quiet,
                        json_progress=json_progress,
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
                            publish_chip_progress(
                                event_type="specialist_dispatched",
                                cli_state=progress_cli_state,
                                mission_id=mission_id,
                                phase=skill_name.replace("chip-", ""),
                                agent=repair_agent,
                                skill=skill_name,
                                status=repair_status or "dispatched",
                                index=step_index,
                                total=len(self.chain),
                                message=f"Failure dispatched to {repair_agent}.",
                                metadata={"output_preview": repair_output[:300]},
                                quiet=quiet,
                                json_progress=json_progress,
                            )
                    failed = True
                    break
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
                publish_chip_progress(
                    event_type="skill_completed",
                    cli_state=progress_cli_state,
                    mission_id=mission_id,
                    phase=skill_name.replace("chip-", ""),
                    agent="eda_agent",
                    skill=skill_name,
                    status="completed",
                    index=step_index,
                    total=len(self.chain),
                    message=f"{skill_name} completed.",
                    metadata={"output_preview": text[:300]},
                    quiet=quiet,
                    json_progress=json_progress,
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
                specialist = FAILURE_SPECIALISTS.get(skill_name, "")
                publish_chip_progress(
                    event_type="skill_failed",
                    cli_state=progress_cli_state,
                    mission_id=mission_id,
                    phase=skill_name.replace("chip-", ""),
                    agent="eda_agent",
                    skill=skill_name,
                    status="failed",
                    index=step_index,
                    total=len(self.chain),
                    message=last_error[:500],
                    fix_request={
                        "failure_type": skill_name,
                        "log_excerpt": last_error[:1200],
                        "target_agent": specialist,
                    },
                    quiet=quiet,
                    json_progress=json_progress,
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
                        publish_chip_progress(
                            event_type="specialist_dispatched",
                            cli_state=progress_cli_state,
                            mission_id=mission_id,
                            phase=skill_name.replace("chip-", ""),
                            agent=repair_agent,
                            skill=skill_name,
                            status=repair_status or "dispatched",
                            index=step_index,
                            total=len(self.chain),
                            message=f"Failure dispatched to {repair_agent}.",
                            metadata={"output_preview": repair_output[:300]},
                            quiet=quiet,
                            json_progress=json_progress,
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


def _skill_execution_failed(result: Any, text: str) -> bool:
    lowered = text.lower()
    if "chip autodesign failed:" in lowered:
        return True
    if "skill 'chip-autodesign' execution error:" in lowered:
        return True
    if "**status:** fail" in lowered and "chip autodesign" in lowered:
        return True
    if isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "chip_autodesign_result":
                payload = item.get("result") or {}
                if str(payload.get("status", "")).upper() != "PASS":
                    return True
            if item.get("type") == "validated_rtl_result":
                payload = item.get("result") or {}
                if str(payload.get("status", "")).upper() == "FAIL":
                    return True
    return False


def _failure_message(result: Any, text: str) -> str:
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and item.get("type") == "chip_autodesign_result":
                payload = item.get("result") or {}
                if payload.get("error"):
                    return str(payload["error"])
    for line in text.splitlines():
        if "failed:" in line.lower() or "execution error:" in line.lower():
            return line.strip()
    return text[:500] or "EDA skill execution failed"


def _verification_target_available(task: str, ctx: Dict[str, Any]) -> bool:
    if ctx.get("dut_path") or ctx.get("project_dir") or ctx.get("resolved_last_rtl"):
        return True
    import re
    if re.search(r"(--dut-path|--project-dir|dut_path|project_dir)\s+\S+", task):
        return True
    if re.search(r"\S+\.(sv|v|svh|vh)\b", task, re.IGNORECASE):
        return True
    try:
        from ...handlers.chip_artifact_resolver import latest_resolved_rtl
        resolved = latest_resolved_rtl(context=ctx, cli_state=ctx.get("cli_state"))
        if resolved:
            ctx["resolved_last_rtl"] = resolved
            return True
    except Exception:
        pass
    return False
