"""
Analog design skill bridge.

Loads analog-chip-design-agents style plugin skills from
deps/analog-chip-design-agents/plugins by default. Override with
ANALOG_CHIP_AGENTS_ROOT.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cktclaw.harness import SkillDefinition, SkillType, LoadedFrom, register_skill


_ANALOG_ROOT = Path(os.environ.get(
    "ANALOG_CHIP_AGENTS_ROOT",
    str(Path(__file__).parent.parent / "deps" / "analog-chip-design-agents" / "plugins"),
))


# (skill_name, plugin_dir, display_name, aliases, description)
_ANALOG_DOMAINS = [
    (
        "analog-design-architecture",
        "analog-design-architecture",
        "Analog Architecture",
        ["analog-architecture", "analog-arch"],
        "Analog architecture exploration, budget allocation, and signal-chain decomposition.",
    ),
    (
        "analog-design-modeling",
        "analog-design-modeling",
        "Analog/AMS Modeling",
        ["analog-modeling", "ams-modeling", "verilog-a"],
        "Behavioral, Verilog-A/AMS, VHDL-AMS, and RNM model generation.",
    ),
    (
        "analog-design-circuit",
        "analog-design-circuit",
        "Analog Circuit Design",
        ["analog-circuit", "schematic-design"],
        "Topology selection, sizing, biasing, schematic planning, and pre-layout review.",
    ),
    (
        "analog-design-simulation",
        "analog-design-simulation",
        "Analog Simulation",
        ["analog-sim", "spice-sim", "ngspice"],
        "DC, AC, transient, noise, corners, Monte Carlo, and electrical signoff.",
    ),
    (
        "analog-design-ams-verification",
        "analog-design-ams-verification",
        "AMS Verification",
        ["ams-verification", "mixed-signal-verification"],
        "AMS testbenches, connect rules, co-simulation, and coverage closure.",
    ),
    (
        "analog-design-layout",
        "analog-design-layout",
        "Analog Layout",
        ["analog-layout", "custom-layout"],
        "Analog layout planning with matching, symmetry, shielding, and routing constraints.",
    ),
    (
        "analog-design-physical-verification",
        "analog-design-physical-verification",
        "Analog Physical Verification",
        ["analog-pv", "drc-lvs"],
        "DRC, LVS, antenna, ERC, density, and DFM signoff.",
    ),
    (
        "analog-design-extraction",
        "analog-design-extraction",
        "Analog Extraction",
        ["analog-pex", "parasitic-extraction"],
        "Parasitic extraction, RC/coupling review, and back-annotated netlists.",
    ),
    (
        "analog-design-post-layout",
        "analog-design-post-layout",
        "Analog Post-Layout",
        ["post-layout", "post-pex"],
        "Post-layout simulation, PEX corner verification, and tape-out gating.",
    ),
    (
        "analog-design-reliability",
        "analog-design-reliability",
        "Analog Reliability",
        ["analog-reliability", "em-ir-esd"],
        "EM, IR-drop, ESD, latch-up, aging, and reliability signoff.",
    ),
    (
        "analog-design-characterization",
        "analog-design-characterization",
        "Analog Characterization",
        ["analog-characterization", "lib-characterization"],
        "Liberty, behavioral model, timing, power, and noise characterization.",
    ),
    (
        "analog-design-rf",
        "analog-design-rf",
        "RF/mmWave Design",
        ["rf-design", "mmwave"],
        "S-parameter, harmonic balance, Pnoise/PAC, IP3, and load-pull workflows.",
    ),
    (
        "analog-design-em",
        "analog-design-em",
        "EM Modeling",
        ["em-modeling", "sparameter"],
        "EM solve planning for passives, antennas, and S-parameter model extraction.",
    ),
    (
        "analog-design-ams-integration",
        "analog-design-ams-integration",
        "AMS Integration",
        ["ams-integration", "analog-ip-integration"],
        "Analog IP qualification, AMS top assembly, and chip-level AMS simulation.",
    ),
    (
        "analog-design-infrastructure",
        "analog-design-infrastructure",
        "Analog Infrastructure",
        ["analog-infra", "analog-tools"],
        "Analog/RF tool detection, wrappers, MCP setup, and memory distillation.",
    ),
    (
        "analog-design-meta",
        "analog-design-meta",
        "Analog Meta Pipeline",
        ["analog-pipeline", "analog-meta"],
        "Closed-loop spec, circuit, layout, extraction, and post-layout orchestration.",
    ),
]


def _first_skill_md(plugin_dir: Path) -> Optional[Path]:
    candidates = [plugin_dir / "SKILL.md"]
    skills_dir = plugin_dir / "skills"
    if skills_dir.is_dir():
        candidates.extend(sorted(skills_dir.glob("*/SKILL.md")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _collect_agent_markdown(plugin_dir: Path) -> str:
    agents_dir = plugin_dir / "agents"
    if not agents_dir.is_dir():
        return ""
    parts: List[str] = []
    for md in sorted(agents_dir.glob("*.md")):
        try:
            parts.append(f"## {md.name}\n\n{md.read_text(encoding='utf-8')}")
        except OSError:
            continue
    return "\n\n---\n\n".join(parts)


def _make_executor(skill_path: Path, plugin_dir: Path, display_name: str):
    async def executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            skill_md = skill_path.read_text(encoding="utf-8")
        except OSError:
            skill_md = f"Skill file not found: {skill_path}"
        agent_md = _collect_agent_markdown(plugin_dir)
        body = f"# {display_name}\n\n{skill_md}"
        if agent_md:
            body += f"\n\n---\n\n# Agents\n\n{agent_md}"
        if args.strip():
            body += f"\n\n---\n\n# User Task\n\n{args.strip()}"
        return [{"type": "text", "text": body}]

    return executor


def _build_skill(
    skill_name: str,
    plugin_name: str,
    display_name: str,
    aliases: List[str],
    description: str,
) -> Optional[SkillDefinition]:
    plugin_dir = _ANALOG_ROOT / plugin_name
    skill_path = _first_skill_md(plugin_dir)
    if skill_path is None:
        return None
    return SkillDefinition(
        name=skill_name,
        skill_type=SkillType.PROMPT,
        description=description,
        display_name=display_name,
        aliases=aliases,
        when_to_use=description,
        argument_hint="Natural language analog/AMS/RF design task",
        argument_names=["task"],
        allowed_tools=["Read", "Write", "Bash"],
        user_invocable=True,
        loaded_from=LoadedFrom.PLUGIN,
        source="analog-chip-design-agents",
        skill_root=str(plugin_dir),
        executor=_make_executor(skill_path, plugin_dir, display_name),
    )


ANALOG_DESIGN_SKILLS = [
    skill for spec in _ANALOG_DOMAINS
    for skill in [_build_skill(*spec)]
    if skill is not None
]


async def register_analog_design_skills() -> int:
    """Register analog-chip-design-agents prompt skills if installed."""
    count = 0
    for skill in ANALOG_DESIGN_SKILLS:
        await register_skill(skill)
        count += 1
    return count
