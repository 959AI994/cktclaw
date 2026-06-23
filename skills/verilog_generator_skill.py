"""
Erie Verilog Generator — bundled PROMPT skill + local tool scripts.

Bundles SKILL.md, runtime/, scripts/, integration/, config/, assets/, references/
under skills/verilog_generator_bundled/. Override with VERILOG_GENERATOR_ROOT.
"""

import asyncio
import os
import shlex
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
from cktclaw.plugins.skill_loader import parse_skill_md

from .prompt_skill_utils import make_prompt_executor

_BUNDLED_DIR = Path(__file__).parent / "verilog_generator_bundled"
_SKILL_NAME = "erie-verilog-generator"

VERILOG_GENERATOR_SKILL_NAMES: set[str] = set()


def get_verilog_generator_root() -> Path:
    """Return active verilog-generator root (bundled or VERILOG_GENERATOR_ROOT)."""
    return _resolve_skill_root()


def _resolve_skill_root() -> Path:
    env_root = os.environ.get("VERILOG_GENERATOR_ROOT", "").strip()
    if env_root:
        ext = Path(env_root).expanduser()
        if (ext / "SKILL.md").is_file():
            return ext
    return _BUNDLED_DIR


def _ensure_root_on_path(root: Path) -> None:
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


async def _run_bundled_script(
    script_rel: str,
    args_str: str,
    label: str,
) -> List[Dict[str, Any]]:
    task_manager = get_task_manager()
    task = await task_manager.create_task(TaskType.LOCAL_BASH, label)
    root = _resolve_skill_root()
    script = root / script_rel

    if not script.is_file():
        msg = f"Script not found: {script}"
        await task_manager.update_task_status(task.task_id, TaskStatus.FAILED)
        return [{"type": "text", "text": msg}]

    parts = shlex.split(args_str.strip()) if args_str.strip() else []
    cmd = [sys.executable, str(script), *parts]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await proc.communicate()
        stdout = stdout_b.decode(errors="replace")
        stderr = stderr_b.decode(errors="replace")
        body = stdout
        if stderr.strip():
            body = f"{stdout}\n\n[stderr]\n{stderr}".strip()
        if proc.returncode != 0:
            body = f"Exit code {proc.returncode}\n\n{body}"
        await task_manager.update_task_status(
            task.task_id,
            TaskStatus.COMPLETED if proc.returncode == 0 else TaskStatus.FAILED,
        )
        return [{"type": "text", "text": body or "(no output)"}]
    except Exception as e:
        await task_manager.update_task_status(task.task_id, TaskStatus.FAILED)
        return [{"type": "text", "text": f"Error running {label}: {e}"}]


def _make_script_tool(
    name: str,
    script_rel: str,
    display_name: str,
    aliases: list,
    description: str,
    when_to_use: str,
    argument_hint: str,
) -> SkillDefinition:
    async def executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        return await _run_bundled_script(script_rel, args, display_name)

    return SkillDefinition(
        name=name,
        skill_type=SkillType.TOOL,
        description=description,
        display_name=display_name,
        aliases=aliases,
        when_to_use=when_to_use,
        argument_hint=argument_hint,
        argument_names=["args"],
        allowed_tools=["Bash"],
        user_invocable=True,
        loaded_from=LoadedFrom.BUNDLED,
        source="verilog-generator",
        skill_root=str(_resolve_skill_root()),
        executor=executor,
    )


def _build_tool_skills() -> List[SkillDefinition]:
    return [
        _make_script_tool(
            "verilog-lint",
            "scripts/verilog_lint.py",
            "Verilog Lint (Erie)",
            ["erie-lint", "verilog-static-lint"],
            "Independent static lint for Verilog-2001 RTL or testbench files (Erie RTL-MD rules).",
            "Use for quick static lint on a .v file without running the full workflow.",
            "Path to .v file, e.g. workspace/adder.v or --mode tb path/to/tb.v",
        ),
        _make_script_tool(
            "verilog-tb-gen",
            "scripts/tb_generator.py",
            "Verilog TB Scaffold (Erie)",
            ["tb-generator", "erie-tb-gen"],
            "Generate a self-checking Verilog testbench scaffold from module ports.",
            "Use when you need a fast self-checking TB scaffold from an RTL .v file.",
            "RTL .v path and optional --output path/to/tb.v",
        ),
    ]


def _build_verilog_generator_skill() -> SkillDefinition:
    skill_root = _resolve_skill_root()
    skill_path = skill_root / "SKILL.md"
    parsed = parse_skill_md(skill_path, "verilog-generator")
    display = parsed.user_facing_name() if parsed else "Erie Verilog Generator"
    description = (
        parsed.description if parsed
        else "Verilog-2001 RTL generation, analysis, verify-repair, and validation workflows."
    )
    when_to_use = parsed.when_to_use if parsed else (
        "Use for disciplined Verilog-2001 RTL design, existing-RTL repair, lint, and testbench scaffolds."
    )

    return SkillDefinition(
        name=_SKILL_NAME,
        skill_type=SkillType.PROMPT,
        description=description,
        display_name="Erie Verilog Generator",
        aliases=["verilog-gen", "verilog-generator", "erie-verilog"],
        when_to_use=when_to_use,
        argument_hint="Natural language Verilog/RTL task, e.g. 'generate a 4-bit adder with self-checking TB'",
        argument_names=["task"],
        allowed_tools=["Read", "Write", "Bash", "verilog-lint", "verilog-tb-gen"],
        user_invocable=True,
        loaded_from=LoadedFrom.BUNDLED,
        source="verilog-generator",
        skill_root=str(skill_root),
        executor=make_prompt_executor(skill_path, display),
    )


async def register_verilog_generator_skill() -> int:
    """Register PROMPT skill + bundled tool scripts (lint, tb scaffold)."""
    global VERILOG_GENERATOR_SKILL_NAMES
    VERILOG_GENERATOR_SKILL_NAMES = set()

    if not (_BUNDLED_DIR / "SKILL.md").is_file():
        print(f"  ⚠ Bundled verilog-generator SKILL.md missing: {_BUNDLED_DIR}")
        return 0
    if not (_BUNDLED_DIR / "runtime" / "verilog_generator").is_dir():
        print(f"  ⚠ Bundled verilog-generator runtime missing under {_BUNDLED_DIR}")
        return 0

    _ensure_root_on_path(_resolve_skill_root())

    count = 0
    for skill in [_build_verilog_generator_skill(), *_build_tool_skills()]:
        await register_skill(skill)
        VERILOG_GENERATOR_SKILL_NAMES.add(skill.name)
        for alias in skill.aliases:
            VERILOG_GENERATOR_SKILL_NAMES.add(alias)
        count += 1
    return count
