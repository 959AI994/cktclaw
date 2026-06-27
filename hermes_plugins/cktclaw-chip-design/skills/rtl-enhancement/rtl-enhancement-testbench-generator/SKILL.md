---
name: rtl-enhancement-testbench-generator
description: Use to create self-checking Verilog/SystemVerilog testbenches for existing RTL.
metadata:
  hermes:
    category: chip-design/rtl-enhancement
    tags: [rtl_enhancement, rtl_enhancement_testbench_generator]
---

# Testbench Generator

## When to Use
Use this skill when the user request matches: Use to create self-checking Verilog/SystemVerilog testbenches for existing RTL.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Identify reset, clock, valid/ready, and output checks.
   - Generate deterministic directed tests before random tests.
   - Compile and run the testbench before handoff.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_iverilog`
- `cktclaw_chip_run_vvp`
- `cktclaw_chip_run_verilator`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
