"""Tests for FPGA-Agent-skills and external SKILL.md search paths."""

import asyncio
from pathlib import Path

_WORKSPACE = Path(__file__).resolve().parents[2]
_FPGA_ROOT = _WORKSPACE / "FPGA-Agent-skills"
_VERILOG_GEN = _WORKSPACE / "verilog-generator"


def test_fpga_skill_md_paths_exist():
    assert _FPGA_ROOT.is_dir(), f"FPGA-Agent-skills not at {_FPGA_ROOT}"
    for sub in (
        "vivado-tcl", "vivado-synth", "vivado-sim", "vivado-impl",
        "vivado-analysis", "vivado-constraints", "vivado-debug",
        "vitis-hls-synthesis",
    ):
        assert (_FPGA_ROOT / sub / "SKILL.md").is_file()


def test_verilog_generator_skill_md_exists():
    assert (_VERILOG_GEN / "SKILL.md").is_file()


def test_discover_skill_md_paths():
    from cktclaw.skills.external_skill_loader import discover_skill_md_paths

    paths = discover_skill_md_paths([_VERILOG_GEN, _FPGA_ROOT])
    names = {p.parent.name if p.parent != _VERILOG_GEN else "erie-root" for p in paths}
    assert any(p == _VERILOG_GEN / "SKILL.md" for p in paths)
    assert "vivado-synth" in names


def test_register_fpga_and_external_skills():
    from cktclaw.harness import get_skill_registry
    from cktclaw.skills.fpga_agent_skills import register_fpga_agent_skills
    from cktclaw.skills.external_skill_loader import register_external_skills

    async def _run():
        await register_fpga_agent_skills()
        await register_external_skills()
        reg = get_skill_registry()
        vivado = await reg.get_skill("vivado-synth")
        assert vivado.executor is not None
        assert vivado.skill_root
        vg = await reg.get_skill("verilog-gen")
        assert vg.name == "erie-verilog-generator"
        assert vg.executor is not None

    asyncio.run(_run())
