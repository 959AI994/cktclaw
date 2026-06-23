"""
FPGA-Agent-skills — 8 Vivado/Vitis PROMPT skills.

SKILL.md is bundled under skills/fpga_agent_bundled/ (pip-install friendly).
Set FPGA_AGENT_SKILLS_ROOT to an external clone for REFERENCE.md / examples.
"""

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cktclaw.harness import (
    SkillDefinition,
    SkillType,
    LoadedFrom,
    register_skill,
)

from .prompt_skill_utils import make_prompt_executor

_SKILLS_DIR = Path(__file__).parent / "fpga_agent_bundled"

# (skill_subdir, name, display_name, aliases, description, when_to_use)
_FPGA_SKILL_SPECS = [
    (
        "vivado-tcl",
        "vivado-tcl",
        "Vivado TCL",
        ["vivado", "xilinx-tcl"],
        "Generate and execute Vivado/Vitis TCL scripts for FPGA flows (project, synth, impl, bitstream).",
        "Use when writing or running Vivado batch TCL, creating projects, or automating Xilinx/AMD FPGA flows.",
    ),
    (
        "vivado-synth",
        "vivado-synth",
        "Vivado Synthesis",
        ["vivado-synthesis"],
        "Vivado synthesis strategy, synth_design options, resource inference (RAM/DSP/BRAM), hierarchy control.",
        "Use when choosing synthesis strategies, attributes, or optimizing area/timing/power in Vivado synthesis.",
    ),
    (
        "vivado-sim",
        "vivado-sim",
        "Vivado Simulation",
        ["vivado-xsim", "xsim"],
        "Vivado/xsim simulation flow setup, compile, elaborate, and run simulation.",
        "Use when setting up or running Vivado behavioral simulation with xsim.",
    ),
    (
        "vivado-impl",
        "vivado-impl",
        "Vivado Implementation",
        ["vivado-implementation", "vivado-place-route"],
        "Vivado place, route, physical optimization, and implementation strategy decisions.",
        "Use when tuning implementation, placement, routing, or phys_opt in Vivado.",
    ),
    (
        "vivado-analysis",
        "vivado-analysis",
        "Vivado Analysis",
        ["vivado-timing", "vivado-reports"],
        "Vivado timing, utilization, power, and report interpretation guidance.",
        "Use when analyzing Vivado timing reports, utilization, or post-route QoR.",
    ),
    (
        "vivado-constraints",
        "vivado-constraints",
        "Vivado Constraints",
        ["vivado-xdc", "xdc"],
        "XDC timing and physical constraints, clock definitions, I/O standards.",
        "Use when writing or debugging XDC constraints for Vivado designs.",
    ),
    (
        "vivado-debug",
        "vivado-debug",
        "Vivado Debug",
        ["vivado-ila", "ila", "vio"],
        "ILA/VIO debug core insertion, trigger setup, and on-chip debug strategy.",
        "Use when adding ILA/VIO, configuring debug cores, or planning FPGA debug.",
    ),
    (
        "vitis-hls-synthesis",
        "vitis-hls-synthesis",
        "Vitis HLS Synthesis",
        ["vitis-hls", "hls-synthesis"],
        "Vitis HLS synthesis pragmas, pipeline, dataflow, and C/C++ kernel optimization.",
        "Use when synthesizing C/C++ kernels with Vitis HLS or tuning HLS directives.",
    ),
]

FPGA_AGENT_SKILL_NAMES: set[str] = set()


def _resolve_skill_dir(skill_subdir: str) -> Path:
    """
    Prefer external FPGA_AGENT_SKILLS_ROOT when it has SKILL.md; else bundled copy.
    """
    env_root = os.environ.get("FPGA_AGENT_SKILLS_ROOT", "").strip()
    if env_root:
        ext = Path(env_root).expanduser() / skill_subdir
        if (ext / "SKILL.md").is_file():
            return ext
    return _SKILLS_DIR / skill_subdir


def _build_fpga_skill(
    skill_subdir: str,
    name: str,
    display_name: str,
    aliases: list,
    description: str,
    when_to_use: str,
) -> SkillDefinition:
    skill_dir = _resolve_skill_dir(skill_subdir)
    skill_path = skill_dir / "SKILL.md"
    return SkillDefinition(
        name=name,
        skill_type=SkillType.PROMPT,
        description=description,
        display_name=display_name,
        aliases=aliases,
        when_to_use=when_to_use,
        argument_hint="Natural language FPGA/Vivado task, e.g. 'synth_design options for area'",
        argument_names=["task"],
        allowed_tools=["Read", "Write", "Bash"],
        user_invocable=True,
        loaded_from=LoadedFrom.BUNDLED,
        source="FPGA-Agent-skills",
        skill_root=str(skill_dir),
        executor=make_prompt_executor(skill_path, display_name),
    )


def _build_all_fpga_skills() -> list[SkillDefinition]:
    return [_build_fpga_skill(*spec) for spec in _FPGA_SKILL_SPECS]


FPGA_AGENT_SKILLS = _build_all_fpga_skills()


async def register_fpga_agent_skills():
    """Register all 8 FPGA-Agent-skills PROMPT skills from bundled SKILL.md."""
    global FPGA_AGENT_SKILL_NAMES
    FPGA_AGENT_SKILL_NAMES = set()

    missing = [
        spec[0] for spec in _FPGA_SKILL_SPECS
        if not (_SKILLS_DIR / spec[0] / "SKILL.md").is_file()
    ]
    if missing:
        print(f"  ⚠ Bundled FPGA skills missing SKILL.md: {', '.join(missing)}")
        return 0

    count = 0
    for skill in _build_all_fpga_skills():
        await register_skill(skill)
        FPGA_AGENT_SKILL_NAMES.add(skill.name)
        for alias in skill.aliases:
            FPGA_AGENT_SKILL_NAMES.add(alias)
        count += 1
    return count
