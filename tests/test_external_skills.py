"""Tests for bundled FPGA / verilog-generator skills and external search paths."""

import asyncio
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[1]
_BUNDLED_FPGA = _PKG_ROOT / "skills" / "fpga_agent_bundled"
_BUNDLED_VG = _PKG_ROOT / "skills" / "verilog_generator_bundled"
_WORKSPACE = Path(__file__).resolve().parents[2]
_EXT_VERILOG_GEN = _WORKSPACE / "verilog-generator"


def test_bundled_fpga_skill_md_paths_exist():
    assert _BUNDLED_FPGA.is_dir()
    for sub in (
        "vivado-tcl", "vivado-synth", "vivado-sim", "vivado-impl",
        "vivado-analysis", "vivado-constraints", "vivado-debug",
        "vitis-hls-synthesis",
    ):
        assert (_BUNDLED_FPGA / sub / "SKILL.md").is_file()


def test_bundled_verilog_generator_skill_md_exists():
    assert (_BUNDLED_VG / "SKILL.md").is_file()


def test_discover_skill_md_paths_external_only():
    from cktclaw.skills.external_skill_loader import discover_skill_md_paths

    paths = discover_skill_md_paths([_EXT_VERILOG_GEN, _BUNDLED_FPGA])
    names = {p.parent.name if p.parent != _EXT_VERILOG_GEN else "erie-root" for p in paths}
    assert any(p == _EXT_VERILOG_GEN / "SKILL.md" for p in paths)
    assert "vivado-synth" in names


def test_bundled_verilog_runtime_and_scripts_exist():
    assert (_BUNDLED_VG / "runtime" / "verilog_generator").is_dir()
    assert (_BUNDLED_VG / "scripts" / "verilog_lint.py").is_file()
    assert (_BUNDLED_VG / "integration" / "verilog_adapter.py").is_file()


def test_register_bundled_skills_without_external_repos():
    from cktclaw.harness import get_skill_registry
    from cktclaw.skills.fpga_agent_skills import register_fpga_agent_skills, _SKILLS_DIR
    from cktclaw.skills.verilog_generator_skill import (
        register_verilog_generator_skill,
        get_verilog_generator_root,
    )
    from cktclaw.skills.external_skill_loader import register_external_skills

    async def _run():
        assert await register_fpga_agent_skills() == 8
        assert await register_verilog_generator_skill() == 3
        await register_external_skills()

        reg = get_skill_registry()
        vivado = await reg.get_skill("vivado-synth")
        assert vivado.skill_root.startswith(str(_SKILLS_DIR))

        vg = await reg.get_skill("verilog-gen")
        assert vg.name == "erie-verilog-generator"
        root = get_verilog_generator_root()
        assert (root / "runtime" / "verilog_generator").is_dir()

        lint = await reg.get_skill("verilog-lint")
        sample = root / "assets" / "examples" / "existing_rtl" / "ready_valid_slice.v"
        result = await lint.executor(str(sample), {})
        assert result[0]["text"]

    asyncio.run(_run())
