"""
System Loop Skill — registers the /loop command for cross-domain closed-loop execution.

Usage: /loop <goal_description> [--iterations N] [--domains eda,chip,ai_infra]
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import asyncio
from typing import Any, Dict, List

from cktclaw.harness import (
    SkillDefinition,
    SkillType,
    LoadedFrom,
    register_skill,
    get_task_manager,
    TaskType,
    TaskStatus,
)


async def system_loop_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    System Loop skill executor.

    Args:
        args: Goal description, optionally followed by --iterations N
        context: Execution context

    Returns:
        Tool result messages.
    """
    if not args.strip():
        return [{
            "type": "text",
            "text": (
                "❌ Please provide a system goal.\n\n"
                "Usage: /loop <goal_description> [--iterations N]\n\n"
                "Examples:\n"
                "  /loop design a 4-bit adder with training pipeline\n"
                "  /loop design a low-power CNN accelerator --iterations 5\n"
                "  /loop create RISC-V ALU with verification and compiler support"
            ),
        }]

    # Parse arguments
    goal, config_overrides = _parse_args(args)

    # Create task
    task_manager = get_task_manager()
    task_handle = await task_manager.create_task(
        TaskType.LOCAL_AGENT,
        f"System Loop: {goal[:50]}..."
    )

    try:
        await task_manager.update_task_status(task_handle.task_id, TaskStatus.RUNNING)
        await task_manager.append_output(
            task_handle.task_id,
            f"🔄 Starting system loop\n"
            f"   Goal: {goal}\n"
            f"   Max iterations: {config_overrides.get('max_iterations', 10)}\n"
        )

        from cktclaw.loop.controller import SystemLoopController, LoopConfig

        config = LoopConfig(
            max_iterations=config_overrides.get("max_iterations", 10),
            domains=config_overrides.get("domains", ["eda", "chip", "ai_infra"]),
        )

        controller = SystemLoopController(config=config)
        result = await controller.run(goal, constraints=config_overrides.get("constraints"))

        # Format result
        if result.status == "converged":
            status_icon = "✅"
            status_text = "CONVERGED"
        elif result.status == "stuck":
            status_icon = "⚠️"
            status_text = "STUCK"
        elif result.status == "timeout":
            status_icon = "⏱️"
            status_text = "TIMEOUT"
        else:
            status_icon = "ℹ️"
            status_text = result.status.upper()

        result_text = (
            f"{status_icon} System Loop {status_text}\n\n"
            f"**Goal**: {goal}\n"
            f"**Iterations**: {result.iterations_completed}/{config.max_iterations}\n"
            f"**Tasks**: {result.passed_tasks}/{result.total_tasks} passed "
            f"({result.success_rate:.0%})\n"
            f"**Duration**: {result.duration_seconds:.1f}s\n"
        )

        if result.artifacts:
            result_text += f"\n**Artifacts** ({len(result.artifacts)}):\n"
            for a in result.artifacts[:10]:
                result_text += f"  - {a}\n"

        await task_manager.update_task_status(task_handle.task_id, TaskStatus.COMPLETED)
        await task_manager.append_output(task_handle.task_id, result_text)

        return [{"type": "text", "text": result_text}]

    except Exception as e:
        await task_manager.update_task_status(task_handle.task_id, TaskStatus.FAILED)
        error_msg = f"❌ System loop failed: {e}"
        await task_manager.append_output(task_handle.task_id, error_msg)
        return [{"type": "text", "text": error_msg}]


def _parse_args(args: str) -> tuple:
    """Parse goal and config overrides from args string."""
    parts = args.split("--")
    goal = parts[0].strip()
    config: Dict[str, Any] = {}

    for part in parts[1:]:
        part = part.strip()
        if part.startswith("iterations"):
            try:
                val = part.split(None, 1)[1].strip()
                config["max_iterations"] = int(val)
            except (IndexError, ValueError):
                pass
        elif part.startswith("domains"):
            try:
                val = part.split(None, 1)[1].strip()
                config["domains"] = [d.strip() for d in val.split(",")]
            except (IndexError, ValueError):
                pass

    return goal, config


SYSTEM_LOOP_SKILL = SkillDefinition(
    name="system-loop",
    skill_type=SkillType.WORKFLOW,
    description="Cross-domain system closed loop: EDA + Chip + AI Infrastructure",
    display_name="System Loop",
    aliases=["loop", "closed-loop", "system-loop"],
    when_to_use=(
        "When the user wants to execute a cross-domain design task that spans "
        "EDA synthesis, chip architecture, and AI infrastructure. "
        "The system loop decomposes goals, generates artifacts in parallel, "
        "verifies with real tools, and iterates until convergence."
    ),
    argument_hint="<goal_description> [--iterations N] [--domains eda,chip,ai_infra]",
    argument_names=["goal", "iterations", "domains"],
    allowed_tools=["Bash", "Read", "Write"],
    user_invocable=True,
    loaded_from=LoadedFrom.BUNDLED,
    executor=system_loop_executor,
)


async def register_system_loop_skill():
    """Register the system loop skill."""
    await register_skill(SYSTEM_LOOP_SKILL)
