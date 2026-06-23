"""Paths for deps/ trees (cloned by setup.sh, same layout as AI4EDA / chip-design-agents)."""

import os
from pathlib import Path

_DEPS_ROOT = Path(__file__).resolve().parent.parent / "deps"


def get_deps_root() -> Path:
    return _DEPS_ROOT


def get_fpga_agent_skills_root() -> Path:
    env = os.environ.get("FPGA_AGENT_SKILLS_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    return _DEPS_ROOT / "FPGA-Agent-skills"


def get_verilog_generator_root() -> Path:
    env = os.environ.get("VERILOG_GENERATOR_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    return _DEPS_ROOT / "verilog-generator"
