"""
CktClaw Skills - EDA 工具技能封装

将所有 EDA 工具封装为标准 Harness Skills
"""

from .abc_skill import ABC_SKILL, register_abc_skill
from .yosys_skill import YOSYS_SKILL, register_yosys_skill
from .reverse_skill import REVERSE_SKILL, register_reverse_skill
from .opensta_skill import OPENSTA_SKILL, register_opensta_skill
from .ai4eda_skill import AI4EDA_SKILL, register as register_ai4eda_skill
from .session_memory_skill import (
    SESSION_MEMORY_SKILL,
    SESSION_MEMORY_LIST_SKILL,
    register as register_session_memory_skill,
)
from .chip_design_skills import CHIP_DESIGN_SKILLS, register_chip_design_skills
from .system_loop_skill import SYSTEM_LOOP_SKILL, register_system_loop_skill
from .rtl_claw_skill import RTL_CLAW_SKILLS, register_rtl_claw_skills
from .fpga_agent_skills import FPGA_AGENT_SKILLS, register_fpga_agent_skills, FPGA_AGENT_SKILL_NAMES
from .verilog_generator_skill import (
    register_verilog_generator_skill,
    VERILOG_GENERATOR_SKILL_NAMES,
    get_verilog_generator_root,
)
from .external_skill_loader import register_external_skills, EXTERNAL_PROMPT_SKILL_NAMES

__all__ = [
    "ABC_SKILL",
    "register_abc_skill",
    "YOSYS_SKILL",
    "register_yosys_skill",
    "REVERSE_SKILL",
    "register_reverse_skill",
    "OPENSTA_SKILL",
    "register_opensta_skill",
    "AI4EDA_SKILL",
    "register_ai4eda_skill",
    "SESSION_MEMORY_SKILL",
    "SESSION_MEMORY_LIST_SKILL",
    "register_session_memory_skill",
    "CHIP_DESIGN_SKILLS",
    "register_chip_design_skills",
    "SYSTEM_LOOP_SKILL",
    "register_system_loop_skill",
    "RTL_CLAW_SKILLS",
    "register_rtl_claw_skills",
    "FPGA_AGENT_SKILLS",
    "register_fpga_agent_skills",
    "FPGA_AGENT_SKILL_NAMES",
    "register_verilog_generator_skill",
    "VERILOG_GENERATOR_SKILL_NAMES",
    "get_verilog_generator_root",
    "register_external_skills",
    "EXTERNAL_PROMPT_SKILL_NAMES",
]
