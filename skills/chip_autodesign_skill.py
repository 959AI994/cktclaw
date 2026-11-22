"""Chip AutoDesign Skill - generic RTL IP design loop."""

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
    text = text.replace("--yes", "").replace("-y", "").replace("--force", "")
    text = text.replace("--quiet", "").replace("--json-progress", "")
    return " ".join(text.split())


async def chip_autodesign_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not args.strip():
        return [{
            "type": "text",
            "text": (
                "Usage: /chip-autodesign <task> [--yes] [--project-dir DIR] "
                "[--max-iters N] [--force]\n\n"
                "Examples:\n"
                "  /chip-autodesign design a sync fifo --yes\n"
                "  /chip-autodesign design an AXI-lite register block --yes\n"
                "  /chip-autodesign design a signed DSP MAC block --yes\n"
                "  /chip-autodesign design a 16x16 Tiny NPU Tile for handwritten digit inference --yes"
            ),
        }]

    task_manager = get_task_manager()
    handle = await task_manager.create_task(
        TaskType.LOCAL_AGENT,
        f"Chip AutoDesign: {args[:50]}...",
    )
    await task_manager.update_task_status(handle.task_id, TaskStatus.RUNNING)

    project_dir = _extract_option(args, "--project-dir")
    try:
        from cktclaw.workflows.chip_autodesign import ChipAutoDesignController

        goal = _strip_flags(args)
        max_iters_raw = _extract_option(args, "--max-iters", "5")
        max_iters = int(max_iters_raw) if max_iters_raw.isdigit() else 5
        force = _flag_present(args, "--force")
        quiet = _flag_present(args, "--quiet")
        json_progress = _flag_present(args, "--json-progress")
        auto_yes = _flag_present(args, "--yes", "-y") or not sys.stdin.isatty()
        cli_state = context.get("cli_state")

        controller = ChipAutoDesignController(
            goal,
            project_dir=project_dir or None,
            max_iterations=max_iters,
            force=force,
            cli_state=cli_state,
            progress_quiet=quiet,
            progress_json=json_progress,
        )

        prepared = controller.prepare()
        if not auto_yes:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.formatted_text import HTML

            console = context.get("cli_state").console if context.get("cli_state") else None
            if console:
                console.print(
                    f"[cyan]Spec:[/cyan] {prepared['spec']}\n"
                    f"[cyan]Plan:[/cyan] {prepared['plan']}"
                )
            session = PromptSession()
            confirm = (await session.prompt_async(
                HTML("<ansicyan>执行 AutoDesign plan？[Y/n]</ansicyan> ❯ "),
                default="Y",
            )).strip().lower()
            if confirm == "n":
                await task_manager.update_task_status(handle.task_id, TaskStatus.COMPLETED)
                return [{"type": "text", "text": f"已生成 spec/plan，未执行。\nSpec: `{prepared['spec']}`\nPlan: `{prepared['plan']}`"}]

        result = await controller.run()
        await task_manager.update_task_status(
            handle.task_id,
            TaskStatus.COMPLETED if result.status == "PASS" else TaskStatus.FAILED,
        )
        return [
            {"type": "text", "text": _build_report(result)},
            {"type": "chip_autodesign_result", "result": result.to_dict()},
        ]
    except Exception as exc:
        await task_manager.update_task_status(handle.task_id, TaskStatus.FAILED)
        fail_payload = {
            "status": "FAIL",
            "error": str(exc),
            "project_dir": project_dir or "",
        }
        return [
            {"type": "text", "text": f"Chip AutoDesign failed: {exc}"},
            {"type": "chip_autodesign_result", "result": fail_payload},
        ]


def _build_report(result) -> str:
    report_path = Path(result.project_dir) / "reports" / "autodesign_report.md"
    lines = [
        "## Chip AutoDesign",
        "",
        f"**Status:** {result.status}",
        f"**Design kind:** `{result.spec.design_kind}`",
        f"**Module:** `{result.spec.module_name}`",
        f"**Project:** `{result.project_dir}`",
        f"**Report:** `{report_path}`",
        "",
        "### Stage Gates",
    ]
    for name, stage in result.stages.items():
        lines.append(f"- `{name}`: {stage.get('status')}")
    lines.extend([
        "",
        "### QoR Snapshot",
        "",
        "```json",
        json.dumps(result.qor, indent=2, ensure_ascii=False),
        "```",
        "",
        "### Coverage Gaps",
    ])
    for gap in result.coverage_gaps:
        lines.append(f"- {gap}")
    lines.extend(["", "### Key Artifacts"])
    for artifact in result.artifacts[:16]:
        lines.append(f"- `{artifact}`")
    if len(result.artifacts) > 16:
        lines.append(f"- ... {len(result.artifacts) - 16} more")
    from cktclaw.workflows.validated_rtl.observability import append_llm_trace_section

    append_llm_trace_section(lines, result.project_dir, overall_status=result.status)
    return "\n".join(lines)


async def register_chip_autodesign_skill() -> None:
    await register_skill(
        SkillDefinition(
            name="chip-autodesign",
            skill_type=SkillType.WORKFLOW,
            description=(
                "Generic RTL IP AutoDesign loop: spec, plan, architecture, RTL, "
                "testbench, simulation, coverage gap, repair request, Yosys QoR, "
                "and signoff report."
            ),
            display_name="Chip AutoDesign",
            aliases=["autodesign", "chip-auto", "auto-rtl"],
            when_to_use=(
                "Use when the user asks for an end-to-end autonomous chip/IP design "
                "flow from natural language through RTL verification and synthesis."
            ),
            argument_hint="<natural language design task> [--yes] [--project-dir DIR]",
            argument_names=["task"],
            allowed_tools=["iverilog", "vvp", "yosys"],
            user_invocable=True,
            loaded_from=LoadedFrom.BUNDLED,
            source="cktclaw",
            executor=chip_autodesign_executor,
        ),
        override=True,
    )
