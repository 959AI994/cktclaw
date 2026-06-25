"""
RTL-CLAW Skills — 5 RTL optimization pipeline skills.

Bundled PROMPT-type skills covering:
  rtl-spec-analyzer → testbench-generator → verilog-partition → verilog-optimization → verilog-merge

Skills load their SKILL.md at import time from the bundled rtl_claw_skills/ directory.
OpenClaw infrastructure (agent_partition.py etc.) is optional — skills degrade gracefully if not present.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List

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

_SKILLS_DIR = Path(__file__).parent / "rtl_claw_skills"

_OPENCLAW_SCRIPTS = ["agent_partition.py", "agent_optimization.py", "agent_merge.py"]


def _openclaw_available() -> bool:
    """Check whether OpenClaw infrastructure is present via RTL_CLAW_ROOT env var."""
    root = os.environ.get("RTL_CLAW_ROOT", "")
    if not root:
        return False
    root_path = Path(root)
    return any((root_path / s).exists() for s in _OPENCLAW_SCRIPTS)


def _make_rtl_executor(skill_subdir: str, display_name: str):
    """
    Factory: returns an async executor for an RTL-CLAW PROMPT skill.

    - Without args: returns SKILL.md content as documentation.
    - With args + OpenClaw available: returns SKILL.md prompt + user args as LLM context.
    - With args + OpenClaw missing: returns MISSING notice + SKILL.md docs.
    """
    skill_path = _SKILLS_DIR / skill_subdir / "SKILL.md"

    async def executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        task_manager = get_task_manager()
        task = await task_manager.create_task(TaskType.LOCAL_BASH, f"{display_name} skill")

        try:
            skill_markdown = (
                skill_path.read_text(encoding="utf-8")
                if skill_path.exists()
                else f"[RTL-CLAW] SKILL.md not found at: {skill_path}"
            )

            # Documentation mode (no user task)
            if not args.strip():
                await task_manager.update_task_status(task.task_id, TaskStatus.COMPLETED)
                return [{"type": "text", "text": f"# {display_name}\n\n{skill_markdown}"}]

            # Execution mode with args
            if not _openclaw_available():
                await task_manager.update_task_status(task.task_id, TaskStatus.COMPLETED)
                return [{"type": "text", "text": (
                    f"[RTL-CLAW: OpenClaw依赖未找到]\n"
                    f"此skill需要 OpenClaw 基础设施 (agent_partition.py 等)。\n"
                    f"请设置 RTL_CLAW_ROOT 环境变量指向 RTL-CLAW 项目根目录，\n"
                    f"或参考 RTL-CLAW README 安装依赖。\n\n"
                    f"--- SKILL 文档 ---\n{skill_markdown}"
                )}]

            # OpenClaw available: return skill prompt + user args as LLM context
            await task_manager.update_task_status(task.task_id, TaskStatus.COMPLETED)
            return [{"type": "text", "text": (
                f"# {display_name}\n\n"
                f"{skill_markdown}\n\n"
                f"---\n\n"
                f"## 用户任务\n\n{args.strip()}"
            )}]

        except Exception as e:
            from ..runtime.run_context import log_exception
            log_exception(
                __name__,
                "RTL-CLAW skill '%s' failed (task %s): %s", display_name, task.task_id, e,
            )
            await task_manager.update_task_status(task.task_id, TaskStatus.FAILED)
            return [{"type": "text", "text": f"Error in {display_name}: {e}"}]

    return executor


# 5 RTL-CLAW skill definitions
_RTL_CLAW_SKILL_SPECS = [
    (
        "rtl-spec-analyzer",
        "rtl-spec-analyzer",
        "RTL Spec Analyzer",
        ["rtl-analyze", "spec-analyze"],
        "Analyze RTL design + specification, extract Signal-to-Pin mappings for downstream testbench generation.",
        "Use when analyzing RTL and specification files to extract module interface info, parse feature points, and map signals to pins.",
    ),
    (
        "testbench-generator",
        "testbench-generator",
        "Testbench Generator",
        ["tb-gen", "testbench-gen"],
        "Generate complete SystemVerilog testbench with stimulus sequences and reference model from rtl-spec-analyzer output.",
        "Use when generating a SystemVerilog testbench from an analysis_result JSON produced by rtl-spec-analyzer.",
    ),
    (
        "verilog-partition",
        "verilog-partition",
        "Verilog Partition",
        ["rtl-partition", "verilog-split"],
        "Split RTL modules into sub-modules by always blocks using the OpenClaw agent_partition script.",
        "Use when splitting a Verilog RTL file into sub-modules by always blocks for optimization.",
    ),
    (
        "verilog-optimization",
        "verilog-optimization",
        "Verilog Optimization",
        ["rtl-opt", "verilog-opt"],
        "Yosys-based optimization of partitioned sub-modules with Verible syntax/lint checks and equivalence verification.",
        "Use when optimizing partitioned Verilog sub-modules after verilog-partition and before verilog-merge.",
    ),
    (
        "verilog-merge",
        "verilog-merge",
        "Verilog Merge",
        ["rtl-merge", "verilog-join"],
        "Merge optimized sub-modules back into complete RTL with equivalence check and iverilog simulation verification.",
        "Use when merging optimized Verilog sub-modules from verilog-partition/verilog-optimization back into a complete module.",
    ),
]


def _build_rtl_skill(
    name: str, skill_subdir: str, display_name: str,
    aliases: list, description: str, when_to_use: str,
) -> SkillDefinition:
    return SkillDefinition(
        name=name,
        skill_type=SkillType.PROMPT,
        description=description,
        display_name=display_name,
        aliases=aliases,
        when_to_use=when_to_use,
        argument_hint="Natural language description of your RTL task, e.g. 'partition workspace/partition_abc123'",
        argument_names=["task"],
        allowed_tools=["Read", "Write", "Bash"],
        user_invocable=True,
        loaded_from=LoadedFrom.BUNDLED,
        source="rtl-claw",
        executor=_make_rtl_executor(skill_subdir, display_name),
    )


RTL_CLAW_SKILLS = [_build_rtl_skill(*spec) for spec in _RTL_CLAW_SKILL_SPECS]


async def register_rtl_claw_skills():
    """Register all 5 RTL-CLAW pipeline skills into the global SkillRegistry."""
    for skill in RTL_CLAW_SKILLS:
        await register_skill(skill)
