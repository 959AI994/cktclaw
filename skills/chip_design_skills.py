"""
Chip Design Skills — 14 domain skills from digital-chip-design-agents.

Each skill loads its SKILL.md content and orchestrator markdown from
/root/digital-chip-design-agents/plugins/<domain>/ and registers it
into the CktClaw SkillRegistry following the harness standard.
"""

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

import os as _os
_AGENTS_ROOT = Path(_os.environ.get(
    "CHIP_AGENTS_ROOT",
    str(Path(__file__).parent.parent.parent.resolve() / "digital-chip-design-agents" / "plugins"),
))

# (domain_dir, skill_subdir, orchestrator_file, skill_name, display_name, aliases, description, when_to_use)
_DOMAINS = [
    (
        "architecture", "architecture", "architecture-orchestrator.md",
        "chip-architecture", "Chip Architecture",
        ["architecture", "arch-design"],
        "Microarchitecture exploration, PPA estimation, risk assessment, and sign-off.",
        "Use when exploring microarchitecture candidates, estimating PPA, or performing architecture risk assessment.",
    ),
    (
        "rtl-design", "rtl-design", "rtl-design-orchestrator.md",
        "chip-rtl", "RTL Design",
        ["rtl", "rtl-design"],
        "SystemVerilog RTL design — module planning, coding standards, lint, CDC, synthesis check.",
        "Use when writing or reviewing RTL, running lint/CDC checks, or preparing RTL for synthesis.",
    ),
    (
        "verification", "functional-verification", "verification-orchestrator.md",
        "chip-verification", "Functional Verification",
        ["verification", "uvm", "coverage"],
        "UVM testbench, test planning, constrained random, coverage closure, regression.",
        "Use when building UVM testbenches, writing tests, closing coverage, or running regression.",
    ),
    (
        "formal", "formal-verification", "formal-orchestrator.md",
        "chip-formal", "Formal Verification",
        ["formal", "fpv", "lec"],
        "Formal property verification (FPV) and logical equivalence checking (LEC).",
        "Use when setting up FPV properties, running formal proofs, or verifying LEC equivalence.",
    ),
    (
        "synthesis", "logic-synthesis", "synthesis-orchestrator.md",
        "chip-synthesis", "Logic Synthesis",
        ["synthesis", "synth", "logic-synthesis"],
        "Logic synthesis — SDC constraints, compile optimization, netlist QC and LEC.",
        "Use when synthesising RTL to gate-level netlist, setting up SDC constraints, or optimising for timing/area/power.",
    ),
    (
        "dft", "dft", "dft-orchestrator.md",
        "chip-dft", "Design for Test",
        ["dft", "scan", "atpg"],
        "Design for Test — scan insertion, ATPG, MBIST, JTAG boundary scan.",
        "Use when inserting scan chains, generating ATPG patterns, setting up MBIST, or configuring JTAG.",
    ),
    (
        "sta", "sta", "sta-orchestrator.md",
        "chip-sta", "Static Timing Analysis",
        ["sta", "timing", "chip-sta"],
        "Static timing analysis — multi-corner analysis, exception review, ECO guidance.",
        "Use when running STA, reviewing timing exceptions, or guiding timing ECOs.",
    ),
    (
        "hls", "hls", "hls-orchestrator.md",
        "chip-hls", "High-Level Synthesis",
        ["hls", "c2rtl"],
        "High-level synthesis — C/C++ to RTL, directive optimization, co-simulation.",
        "Use when converting C/C++ to RTL, optimising HLS directives, or running co-simulation.",
    ),
    (
        "pd", "physical-design", "physical-design-orchestrator.md",
        "chip-pd", "Physical Design",
        ["pd", "physical-design", "floorplan"],
        "Physical design — floorplan, placement, CTS, routing, timing/power/area opt, sign-off.",
        "Use when running physical design flows from floorplan through routing and sign-off.",
    ),
    (
        "soc", "soc-integration", "soc-integration-orchestrator.md",
        "chip-soc", "SoC Integration",
        ["soc", "ip-integration"],
        "SoC IP integration — procurement, bus fabric, chip-level simulation.",
        "Use when integrating IPs, configuring bus fabric, or running chip-level simulation.",
    ),
    (
        "compiler", "compiler-toolchain", "compiler-orchestrator.md",
        "chip-compiler", "Compiler Toolchain",
        ["compiler", "llvm-backend"],
        "Compiler toolchain — LLVM/GCC backend, assembler, linker, runtime libs for custom ISA.",
        "Use when developing compiler backends, assemblers, linkers, or runtime libraries for a custom ISA.",
    ),
    (
        "firmware", "embedded-firmware", "firmware-orchestrator.md",
        "chip-firmware", "Embedded Firmware",
        ["firmware", "bsp", "drivers"],
        "Embedded firmware — BSP, peripheral drivers, RTOS integration, validation.",
        "Use when developing BSP, peripheral drivers, RTOS integration, or firmware validation.",
    ),
    (
        "fpga", "fpga-emulation", "fpga-orchestrator.md",
        "chip-fpga", "FPGA Emulation",
        ["fpga", "fpga-emulation"],
        "FPGA emulation — ASIC-to-FPGA adaptation, partitioning, bring-up, SW validation.",
        "Use when porting ASIC designs to FPGA, partitioning for emulation, or validating on FPGA.",
    ),
    (
        "infrastructure", "infrastructure", "infrastructure-orchestrator.md",
        "chip-infrastructure", "EDA Infrastructure",
        ["chip-infra", "eda-setup"],
        "EDA tool detection, output-filtering shell wrappers, and MCP server config templates.",
        "Use when setting up EDA tools, deploying wrappers, or configuring MCP servers.",
    ),
]


def _make_executor(
    skill_path: Path,
    orchestrator_path: Path,
    display_name: str,
    skill_name: str,
):
    """Factory: returns an async executor.

    - Without args: returns SKILL.md + orchestrator markdown (documentation mode).
    - With args: runs the full orchestrator state-machine flow via LLM.
    """
    async def executor(args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        task_manager = get_task_manager()
        task = await task_manager.create_task(TaskType.LOCAL_BASH, f"{display_name} skill")

        try:
            content = skill_path.read_text() if skill_path.exists() else f"Skill file not found: {skill_path}"
            orch_content = orchestrator_path.read_text() if orchestrator_path.exists() else ""

            # ── Documentation mode (no user task) ──────────────────────
            if not args.strip():
                text = f"# {display_name}\n\n{content}"
                if orch_content:
                    text += f"\n\n---\n\n## Orchestrator\n\n{orch_content}"
                await task_manager.update_task_status(task.task_id, TaskStatus.COMPLETED)
                return [{"type": "text", "text": text}]

            # ── Orchestrator execution mode ────────────────────────────
            if not orch_content or not orchestrator_path.exists():
                await task_manager.update_task_status(task.task_id, TaskStatus.COMPLETED)
                return [{"type": "text", "text": f"No orchestrator found for {display_name}; showing skill docs.\n\n{content}"}]

            cli_state = context.get("cli_state")
            if cli_state is None:
                await task_manager.update_task_status(task.task_id, TaskStatus.FAILED)
                return [{"type": "text", "text": "Error: cli_state not available in context."}]

            from cktclaw.orchestrator import parse_orchestrator, OrchestratorEngine
            from cktclaw.eda_tools.tool_detection import detect_all_tools
            from cktclaw.mcp.mcp_config import generate_mcp_configs, write_internal_mcp_config
            from cktclaw.mcp.mcp_manager import MCPServerManager

            spec = parse_orchestrator(orchestrator_path)

            # Lazy-init tool manifest (cached on cli_state)
            manifest = getattr(cli_state, '_tool_manifest', None)
            if manifest is None:
                manifest = detect_all_tools()
                cli_state._tool_manifest = manifest

            # Lazy-init MCP manager (cached on cli_state)
            mcp_mgr = getattr(cli_state, '_mcp_manager', None)
            if mcp_mgr is None:
                servers = generate_mcp_configs(manifest)
                mcp_cfg_path = Path(__file__).parent.parent / "mcp" / "mcp-servers.json"
                write_internal_mcp_config(servers, mcp_cfg_path)
                mcp_mgr = MCPServerManager(mcp_cfg_path)
                cli_state._mcp_manager = mcp_mgr

            engine = OrchestratorEngine(
                spec=spec,
                skill_md=content,
                cli_state=cli_state,
                manifest=manifest,
                mcp_manager=mcp_mgr,
            )

            snapshot = await engine.run(args.strip())

            await task_manager.update_task_status(task.task_id, TaskStatus.COMPLETED)
            import json
            return [{"type": "text", "text": f"## Orchestrator Complete\n\n```json\n{json.dumps(snapshot, indent=2)}\n```"}]

        except Exception as e:
            await task_manager.update_task_status(task.task_id, TaskStatus.FAILED)
            return [{"type": "text", "text": f"Error in {display_name}: {e}"}]

    return executor


def _build_skill(domain_dir, skill_subdir, orchestrator_file,
                 name, display_name, aliases, description, when_to_use) -> SkillDefinition:
    skill_path = _AGENTS_ROOT / domain_dir / "skills" / skill_subdir / "SKILL.md"
    orch_path = _AGENTS_ROOT / domain_dir / "agents" / orchestrator_file
    return SkillDefinition(
        name=name,
        skill_type=SkillType.WORKFLOW,
        description=description,
        display_name=display_name,
        aliases=aliases,
        when_to_use=when_to_use,
        argument_hint="Natural language description of your design task, e.g. 'synthesise my AXI DMA controller with ASAP7'",
        argument_names=["task"],
        allowed_tools=["Read", "Write", "Bash"],
        user_invocable=True,
        loaded_from=LoadedFrom.PLUGIN,
        source="digital-chip-design-agents",
        executor=_make_executor(skill_path, orch_path, display_name, name),
    )


# Build all skill definitions
CHIP_DESIGN_SKILLS = [_build_skill(*d) for d in _DOMAINS]


async def register_chip_design_skills():
    """Register all 14 chip design domain skills."""
    for skill in CHIP_DESIGN_SKILLS:
        await register_skill(skill)
