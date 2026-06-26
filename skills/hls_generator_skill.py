"""
HLS Generator - PROMPT skill bridge.

Loads Eriemon/hls-generator from deps/hls-generator by default. Override with
HLS_GENERATOR_ROOT.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cktclaw.harness import SkillDefinition, SkillType, LoadedFrom, register_skill
from cktclaw.plugins.skill_loader import parse_skill_md

from .deps_roots import get_hls_generator_root as _resolve_hls_root
from .prompt_skill_utils import make_prompt_executor

_SKILL_NAME = "hls-generator"

HLS_GENERATOR_SKILL_NAMES: set[str] = set()


def get_hls_generator_root() -> Path:
    return _resolve_hls_root()


def _ensure_root_on_path(root: Path) -> None:
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _build_hls_generator_skill() -> SkillDefinition:
    skill_root = _resolve_hls_root()
    skill_path = skill_root / "SKILL.md"
    parsed = parse_skill_md(skill_path, "hls-generator")
    display = parsed.user_facing_name() if parsed else "HLS Generator"
    description = (
        parsed.description if parsed
        else "Structured Vitis HLS design, interface, pragma, Tcl, and validation workflows."
    )
    when_to_use = parsed.when_to_use if parsed else (
        "Use for Vitis HLS C/C++ kernels, testbenches, Tcl generation, pragma choices, "
        "and report-driven HLS debugging."
    )

    return SkillDefinition(
        name=_SKILL_NAME,
        skill_type=SkillType.PROMPT,
        description=description,
        display_name="HLS Generator",
        aliases=["hls-gen", "vitis-hls-generator", "vitis-hls"],
        when_to_use=when_to_use,
        argument_hint="Natural language HLS task, e.g. 'create a streaming FIR kernel with testbench'",
        argument_names=["task"],
        allowed_tools=["Read", "Write", "Bash"],
        user_invocable=True,
        loaded_from=LoadedFrom.BUNDLED,
        source="hls-generator",
        skill_root=str(skill_root),
        executor=make_prompt_executor(skill_path, display),
    )


async def register_hls_generator_skill() -> int:
    """Register HLS Generator prompt skill when the dependency is present."""
    global HLS_GENERATOR_SKILL_NAMES
    HLS_GENERATOR_SKILL_NAMES = set()

    root = _resolve_hls_root()
    if not (root / "SKILL.md").is_file():
        print(f"  HLS generator not found at {root} (set HLS_GENERATOR_ROOT or clone deps/hls-generator)")
        return 0
    if not (root / "runtime" / "hls_generator").is_dir():
        print(f"  HLS generator runtime missing under {root}")
        return 0

    _ensure_root_on_path(root)
    skill = _build_hls_generator_skill()
    await register_skill(skill)
    HLS_GENERATOR_SKILL_NAMES.add(skill.name)
    for alias in skill.aliases:
        HLS_GENERATOR_SKILL_NAMES.add(alias)
    return 1
