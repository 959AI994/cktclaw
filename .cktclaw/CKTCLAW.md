# CktClaw Project Constitution

## Project Identity
This is the CktClaw EDA platform — an autonomous multi-agent ecosystem for intelligent circuit analysis.

## Coding Standards
- All Python code must use type hints and asyncio
- Follow the Provider architecture pattern for LLM integrations
- Use SkillRegistry for all tool registrations

## EDA Conventions
- Default library: ASAP7
- AIG files should be processed through LogicRT first
- Always report area/delay metrics in Chinese summaries

## Chip Design Domain Skills (digital-chip-design-agents)

When a user describes a chip design task in natural language, automatically load the matching skill
and follow its domain rules before executing. Do NOT ask the user to invoke a command — just load
the skill and proceed.

| User intent | Skill to load |
|---|---|
| microarchitecture, PPA estimation, architecture exploration | chip-architecture |
| RTL coding, SystemVerilog, lint, CDC | chip-rtl |
| UVM testbench, coverage, regression | chip-verification |
| formal verification, FPV, LEC equivalence | chip-formal |
| logic synthesis, SDC constraints, netlist | chip-synthesis |
| DFT, scan insertion, ATPG, JTAG | chip-dft |
| static timing analysis, timing ECO | chip-sta |
| high-level synthesis, C/C++ to RTL | chip-hls |
| physical design, floorplan, placement, routing | chip-pd |
| SoC integration, IP integration, bus fabric | chip-soc |
| compiler toolchain, LLVM, GCC backend | chip-compiler |
| embedded firmware, BSP, drivers, RTOS | chip-firmware |
| FPGA emulation, ASIC-to-FPGA porting | chip-fpga |
| EDA tool setup, wrapper deployment, MCP config | chip-infrastructure |

## Available Orchestrator Agents

Invoke these agents for full end-to-end flows:
- `chip-architecture` — architecture-orchestrator
- `chip-rtl` — rtl-design-orchestrator
- `chip-verification` — verification-orchestrator
- `chip-formal` — formal-orchestrator
- `chip-synthesis` — synthesis-orchestrator (stages: constraint_setup → compile_explore → compile_final → netlist_qc → synthesis_signoff)
- `chip-dft` — dft-orchestrator
- `chip-sta` — sta-orchestrator
- `chip-hls` — hls-orchestrator
- `chip-pd` — physical-design-orchestrator
- `chip-soc` — soc-integration-orchestrator
- `chip-compiler` — compiler-orchestrator
- `chip-firmware` — firmware-orchestrator
- `chip-fpga` — fpga-orchestrator
- `chip-infrastructure` — infrastructure-orchestrator

