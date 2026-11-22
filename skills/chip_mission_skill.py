"""Chip Mission Skill - PM-led adaptive multi-agent chip task control."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from cktclaw.harness import (
    LoadedFrom,
    SkillDefinition,
    SkillType,
    TaskStatus,
    TaskType,
    get_task_manager,
    register_skill,
)


def _flag_present(args: str, *names: str) -> bool:
    tokens = set(args.split())
    return any(name in tokens for name in names)


def _extract_option(args: str, name: str, default: str = "") -> str:
    m = re.search(rf"{re.escape(name)}(?:=|\s+)([^\s]+)", args)
    return m.group(1).strip() if m else default


def _strip_flags(args: str) -> str:
    text = re.sub(r"--project-dir(?:=|\s+)[^\s]+", "", args)
    text = re.sub(r"--max-iters(?:=|\s+)[^\s]+", "", text)
    text = re.sub(r"--max-mission-rounds(?:=|\s+)[^\s]+", "", text)
    text = text.replace("--yes", "").replace("-y", "").replace("--force", "")
    text = text.replace("--quiet", "").replace("--json-progress", "")
    return " ".join(text.split())


async def chip_mission_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not args.strip():
        return [{
            "type": "text",
            "text": (
                "Usage: /chip-mission <task> [--yes] [--project-dir DIR] "
                "[--max-iters N] [--force]\n\n"
                "Examples:\n"
                "  /chip-mission design a sync fifo with verification and synthesis --yes\n"
                "  /chip-mission create a Tiny NPU Tile for handwritten digit inference --yes\n"
                "  /chip-mission build an AXI-lite register block and driver plan --yes"
            ),
        }]

    task_manager = get_task_manager()
    handle = await task_manager.create_task(TaskType.LOCAL_AGENT, f"Chip Mission: {args[:50]}...")
    await task_manager.update_task_status(handle.task_id, TaskStatus.RUNNING)
    try:
        from cktclaw.agents.mission_control import ChipMissionControl

        goal = _strip_flags(args)
        project_dir = _extract_option(args, "--project-dir")
        max_iters_raw = _extract_option(args, "--max-iters", "5")
        max_iters = int(max_iters_raw) if max_iters_raw.isdigit() else 5
        max_rounds_raw = _extract_option(args, "--max-mission-rounds", "-1")
        max_mission_rounds = int(max_rounds_raw) if max_rounds_raw.lstrip("-").isdigit() else -1
        force = _flag_present(args, "--force")
        quiet = _flag_present(args, "--quiet")
        json_progress = _flag_present(args, "--json-progress")
        auto_yes = _flag_present(args, "--yes", "-y") or not sys.stdin.isatty()
        cli_state = context.get("cli_state")

        mission = ChipMissionControl(
            goal,
            cli_state=cli_state,
            project_dir=project_dir or None,
            force=force,
            max_iterations=max_iters,
            max_mission_rounds=max_mission_rounds,
            progress_quiet=quiet,
            progress_json=json_progress,
        )
        prepared = mission.prepare()
        if not auto_yes:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.formatted_text import HTML

            console = getattr(cli_state, "console", None)
            if console:
                console.print(
                    f"[cyan]Mission spec:[/cyan] {prepared['mission_spec']}\n"
                    f"[cyan]Agent plan:[/cyan] {prepared['agent_plan']}"
                )
            session = PromptSession()
            confirm = (await session.prompt_async(
                HTML("<ansicyan>执行 Chip Mission agent plan？[Y/n]</ansicyan> ❯ "),
                default="Y",
            )).strip().lower()
            if confirm == "n":
                await task_manager.update_task_status(handle.task_id, TaskStatus.COMPLETED)
                return [{"type": "text", "text": f"已生成 mission spec/agent plan，未执行。\nSpec: `{prepared['mission_spec']}`\nPlan: `{prepared['agent_plan']}`"}]

        result = await mission.run()
        await task_manager.update_task_status(
            handle.task_id,
            TaskStatus.COMPLETED if result.status == "PASS" else TaskStatus.FAILED,
        )
        return [
            {"type": "text", "text": _build_report(result)},
            {"type": "chip_mission_result", "result": result.to_dict()},
        ]
    except Exception as exc:
        await task_manager.update_task_status(handle.task_id, TaskStatus.FAILED)
        return [{"type": "text", "text": f"Chip Mission failed: {exc}"}]


def _build_report(result) -> str:
    lines = [
        "## Chip Mission",
        "",
        f"**Status:** {result.status}",
        f"**Mission type:** `{result.mission_type}`",
        f"**Mission id:** `{result.mission_id}`",
        f"**Report:** `{result.report_path}`",
        "",
        "### Agent Phases",
    ]
    for phase in result.phases:
        lines.append(f"- `{phase.role_id}` / `{phase.phase}`: {phase.status}")
    lines.extend(["", "### Agent Plan JSON", "", "```json"])
    lines.append(json.dumps([s.to_dict() for s in result.agent_plan], indent=2, ensure_ascii=False))
    lines.extend(["```", "", "### Key Artifacts"])
    for artifact in result.artifacts[:16]:
        lines.append(f"- `{artifact}`")
    if len(result.artifacts) > 16:
        lines.append(f"- ... {len(result.artifacts) - 16} more")
    from cktclaw.workflows.validated_rtl.observability import append_llm_trace_section

    mission_root = Path(result.report_path).parent if result.report_path else None
    append_llm_trace_section(lines, mission_root, overall_status=result.status)
    return "\n".join(lines)


async def register_chip_mission_skill() -> None:
    await register_skill(
        SkillDefinition(
            name="chip-mission",
            skill_type=SkillType.WORKFLOW,
            description=(
                "PM-led adaptive multi-agent chip mission controller. It diagnoses "
                "the task, chooses agents/skills/tools, executes suitable stages, "
                "records evidence, and dispatches failures to specialists."
            ),
            display_name="Chip Mission Control",
            aliases=["mission", "auto-chip", "chip-agent"],
            when_to_use=(
                "Use for broad or complex chip tasks that should be handled by the "
                "multi-agent system rather than one fixed chip-* domain skill."
            ),
            argument_hint="<natural language chip task> [--yes] [--project-dir DIR]",
            argument_names=["task"],
            allowed_tools=["Agent", "SendMessage", "TaskStop", "chip-autodesign"],
            user_invocable=True,
            loaded_from=LoadedFrom.BUNDLED,
            source="cktclaw",
            executor=chip_mission_executor,
        ),
        override=True,
    )
