"""
Chip System Skill — /chip-system seven-agent multi-agent pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cktclaw.harness import (
    SkillDefinition,
    SkillType,
    LoadedFrom,
    register_skill,
    get_task_manager,
    TaskType,
    TaskStatus,
)


def _parse_args(args: str) -> tuple[str, str]:
    text = args.strip()
    mode = "full"
    if "--eda-only" in text:
        mode = "eda_only"
        text = text.replace("--eda-only", "").strip()
    return text, mode


async def chip_system_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not args.strip():
        return [{
            "type": "text",
            "text": (
                "❌ Please provide a system design goal.\n\n"
                "Usage: /chip-system <goal> [--eda-only]\n\n"
                "Examples:\n"
                "  /chip-system design 8-bit adder from architecture to deploy, workdir ./designs/adder_8bit/\n"
                "  /chip-system full SoC accelerator flow with PPA targets\n"
                "  /chip-system RTL through signoff --eda-only"
            ),
        }]

    goal, mode = _parse_args(args)
    task_manager = get_task_manager()
    handle = await task_manager.create_task(
        TaskType.LOCAL_AGENT,
        f"Chip System: {goal[:50]}...",
    )

    try:
        await task_manager.update_task_status(handle.task_id, TaskStatus.RUNNING)
        cli_state = context.get("cli_state")

        from cktclaw.agents.multi_agent_orchestrator import MultiAgentOrchestrator
        from cktclaw.orchestrator.artifacts import build_completion_report

        orchestrator = MultiAgentOrchestrator(cli_state=cli_state)
        result = await orchestrator.run(goal, mode=mode)  # type: ignore[arg-type]

        report = _build_report(result)
        await task_manager.update_task_status(handle.task_id, TaskStatus.COMPLETED)
        return [
            {"type": "text", "text": report},
            {"type": "multi_agent_result", "result": result.to_dict()},
        ]
    except Exception as e:
        await task_manager.update_task_status(handle.task_id, TaskStatus.FAILED)
        return [{"type": "text", "text": f"Chip System failed: {e}"}]


def _build_report(result) -> str:
    lines = [
        f"## Chip System 完成 — 七 Agent 流水线",
        "",
        f"**Session:** `{result.session_id}`",
        f"**Status:** {result.status}",
        f"**Optimization rounds:** {result.optimization_rounds}",
        "",
        "### 系统规格书（摘要）",
        result.spec_markdown[:1500] if result.spec_markdown else "（无）",
        "",
        "### 各阶段结果",
    ]
    for p in result.phases:
        icon = "✅" if p.status == "completed" else "⚠️" if p.status != "failed" else "❌"
        lines.append(f"- {icon} **{p.role_id}** (`{p.phase}`): {p.status}")
        if p.error:
            lines.append(f"  - error: {p.error[:200]}")
    lines.extend(["", "### 技术详情 (JSON)", "", "```json"])
    import json
    lines.append(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    lines.append("```")
    return "\n".join(lines)


async def register_chip_system_skill() -> None:
    skill = SkillDefinition(
        name="chip-system",
        skill_type=SkillType.WORKFLOW,
        description=(
            "Full-stack seven-agent pipeline: PM → Architect → EDA → Compiler/Runtime "
            "→ Deploy → Optimizer with optional iteration loop."
        ),
        display_name="Chip System (7-Agent)",
        aliases=["multi-agent", "chip-system", "seven-agent"],
        when_to_use=(
            "Use for end-to-end chip/system design from requirements through deployment "
            "and optimization, coordinating PMAgent and six specialists."
        ),
        user_invocable=True,
        loaded_from=LoadedFrom.BUILTIN,
        executor=chip_system_executor,
    )
    await register_skill(skill)
