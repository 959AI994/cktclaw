"""
Erie Verilog Generator — WORKFLOW skill + local tool scripts.

Loads from deps/verilog-generator/ (cloned by setup.sh).
Override with VERILOG_GENERATOR_ROOT.
"""

import asyncio
import re
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

from .deps_roots import get_verilog_generator_root as _resolve_vg_root

_SKILL_NAME = "erie-verilog-generator"

VERILOG_GENERATOR_SKILL_NAMES: set[str] = set()


def get_verilog_generator_root() -> Path:
    return _resolve_vg_root()


def _ensure_root_on_path(root: Path) -> None:
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _flag_present(args: str, *names: str) -> bool:
    tokens = set(args.split())
    return any(name in tokens for name in names)


def _extract_option(args: str, name: str, default: str = "") -> str:
    match = re.search(rf"{re.escape(name)}(?:=|\s+)([^\s]+)", args)
    return match.group(1).strip() if match else default


def _strip_flags(args: str) -> str:
    text = re.sub(r"--project-dir(?:=|\s+)[^\s]+", "", args)
    text = re.sub(r"--max-repair-rounds(?:=|\s+)[^\s]+", "", text)
    text = text.replace("--show-skill-doc", "")
    text = text.replace("--mock-provider", "")
    text = text.replace("--yes", "").replace("-y", "").replace("--force", "")
    return " ".join(text.split())


async def _run_bundled_script(
    script_rel: str,
    args_str: str,
    label: str,
) -> List[Dict[str, Any]]:
    task_manager = get_task_manager()
    task = await task_manager.create_task(TaskType.LOCAL_BASH, label)
    root = _resolve_vg_root()
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
        skill_root=str(_resolve_vg_root()),
        executor=executor,
    )


async def erie_verilog_executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    skill_root = _resolve_vg_root()
    skill_path = skill_root / "SKILL.md"
    parsed = parse_skill_md(skill_path, "verilog-generator")
    display = parsed.user_facing_name() if parsed else "Erie Verilog Generator"

    if _flag_present(args, "--show-skill-doc") or not args.strip():
        if not skill_path.is_file():
            return [{"type": "text", "text": f"SKILL.md not found under {skill_root}"}]
        body = skill_path.read_text(encoding="utf-8", errors="replace")
        if args.strip() and not _flag_present(args, "--show-skill-doc"):
            return [{
                "type": "text",
                "text": (
                    f"Usage: /{_SKILL_NAME} <task> [--project-dir DIR] "
                    "[--max-repair-rounds N] [--mock-provider] [--force]\n\n"
                    "Add --show-skill-doc to view the bundled skill documentation."
                ),
            }]
        return [{"type": "skill_doc", "text": f"# {display}\n\n{body}"}]

    task_manager = get_task_manager()
    handle = await task_manager.create_task(
        TaskType.LOCAL_AGENT,
        f"Erie Verilog: {args[:60]}...",
    )
    await task_manager.update_task_status(handle.task_id, TaskStatus.RUNNING)

    try:
        from cktclaw.workflows.validated_rtl import ValidatedRTLController

        goal = _strip_flags(args)
        project_dir = _extract_option(args, "--project-dir")
        max_repair_raw = _extract_option(args, "--max-repair-rounds", "5")
        max_repair_rounds = int(max_repair_raw) if max_repair_raw.isdigit() else 5
        use_mock = _flag_present(args, "--mock-provider")
        cli_state = context.get("cli_state")
        provider_name = None
        if cli_state is not None and hasattr(cli_state, "router"):
            try:
                provider_name = cli_state.router.current_name
            except Exception:
                provider_name = None

        controller = ValidatedRTLController(
            goal,
            project_dir=project_dir or None,
            max_repair_rounds=max_repair_rounds,
            provider_name=provider_name,
            use_mock_provider=use_mock,
            cli_state=cli_state,
            force=_flag_present(args, "--force"),
        )
        result = await controller.run()
        await task_manager.update_task_status(
            handle.task_id,
            TaskStatus.COMPLETED if result.status == "PASS" else TaskStatus.FAILED,
        )
        return [{
            "type": "validated_rtl_result",
            "text": result.summary,
            "result": result.to_dict(),
        }]
    except Exception as exc:
        await task_manager.update_task_status(handle.task_id, TaskStatus.FAILED)
        return [{"type": "text", "text": f"Erie Verilog execution failed: {exc}"}]


def _build_verilog_generator_skill() -> SkillDefinition:
    skill_root = _resolve_vg_root()
    skill_path = skill_root / "SKILL.md"
    parsed = parse_skill_md(skill_path, "verilog-generator")
    description = (
        parsed.description if parsed
        else "Verilog-2001 RTL generation, analysis, verify-repair, and validation workflows."
    )
    when_to_use = parsed.when_to_use if parsed else (
        "Use for disciplined Verilog-2001 RTL design, existing-RTL repair, lint, and testbench scaffolds."
    )

    return SkillDefinition(
        name=_SKILL_NAME,
        skill_type=SkillType.WORKFLOW,
        description=description,
        display_name="Erie Verilog Generator",
        aliases=["verilog-gen", "verilog-generator", "erie-verilog"],
        when_to_use=when_to_use,
        argument_hint=(
            "Natural language Verilog/RTL task, e.g. "
            "'design crc8_stream_accel with self-checking TB, sim, Yosys, repair, hard gate report'"
        ),
        argument_names=["task"],
        allowed_tools=["Read", "Write", "Bash", "verilog-lint", "verilog-tb-gen"],
        user_invocable=True,
        loaded_from=LoadedFrom.BUNDLED,
        source="verilog-generator",
        skill_root=str(skill_root),
        executor=erie_verilog_executor,
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


async def register_verilog_generator_skill() -> int:
    """Register WORKFLOW skill + tool scripts from deps/verilog-generator."""
    global VERILOG_GENERATOR_SKILL_NAMES
    VERILOG_GENERATOR_SKILL_NAMES = set()

    root = _resolve_vg_root()
    if not (root / "SKILL.md").is_file():
        print(f"  ⚠ verilog-generator not found at {root} (run setup.sh or set VERILOG_GENERATOR_ROOT)")
        return 0
    if not (root / "runtime" / "verilog_generator").is_dir():
        print(f"  ⚠ verilog-generator runtime missing under {root}")
        return 0

    _ensure_root_on_path(root)

    preflight = None
    try:
        from cktclaw.workflows.validated_rtl.adapter_loader import ensure_verilog_adapter_available
        preflight = ensure_verilog_adapter_available()
        if not preflight.ok:
            print(f"  ⚠ verilog_adapter preflight failed: {preflight.error}")
            print(f"    {preflight.hint}")
    except Exception as exc:
        print(f"  ⚠ verilog_adapter preflight error: {exc}")

    count = 0
    for skill in [_build_verilog_generator_skill(), *_build_tool_skills()]:
        await register_skill(skill)
        VERILOG_GENERATOR_SKILL_NAMES.add(skill.name)
        for alias in skill.aliases:
            VERILOG_GENERATOR_SKILL_NAMES.add(alias)
        count += 1
    return count
