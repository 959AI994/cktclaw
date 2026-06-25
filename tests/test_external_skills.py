"""Tests for deps/ skill trees and bundled RTL-CLAW skill registration."""

import asyncio
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[1]
_DEPS_FPGA = _PKG_ROOT / "deps" / "FPGA-Agent-skills"
_DEPS_VG = _PKG_ROOT / "deps" / "verilog-generator"


def test_deps_fpga_skill_md_paths_exist():
    assert _DEPS_FPGA.is_dir(), f"Run setup.sh to clone deps/FPGA-Agent-skills ({_DEPS_FPGA})"
    for sub in (
        "vivado-tcl", "vivado-synth", "vivado-sim", "vivado-impl",
        "vivado-analysis", "vivado-constraints", "vivado-debug",
        "vitis-hls-synthesis",
    ):
        assert (_DEPS_FPGA / sub / "SKILL.md").is_file()


def test_deps_verilog_generator_tree_exists():
    assert (_DEPS_VG / "SKILL.md").is_file()
    assert (_DEPS_VG / "runtime" / "verilog_generator").is_dir()
    assert (_DEPS_VG / "scripts" / "verilog_lint.py").is_file()


def test_register_skills_from_deps():
    from cktclaw.harness import get_skill_registry
    from cktclaw.skills.fpga_agent_skills import register_fpga_agent_skills
    from cktclaw.skills.rtl_claw_skill import register_rtl_claw_skills
    from cktclaw.skills.verilog_generator_skill import (
        register_verilog_generator_skill,
        get_verilog_generator_root,
    )

    async def _run():
        await register_rtl_claw_skills()
        assert await register_fpga_agent_skills() == 8
        assert await register_verilog_generator_skill() == 3
        reg = get_skill_registry()
        assert (await reg.get_skill("rtl-spec-analyzer")).name == "rtl-spec-analyzer"
        assert (await reg.get_skill("testbench-generator")).name == "testbench-generator"
        root = get_verilog_generator_root()
        assert root == _DEPS_VG.resolve()
        lint = await reg.get_skill("verilog-lint")
        sample = root / "assets" / "examples" / "existing_rtl" / "ready_valid_slice.v"
        result = await lint.executor(str(sample), {})
        assert result[0]["text"]

    asyncio.run(_run())
