---
name: rtl-enhancement-verilog-optimization
description: Use after RTL partitioning to optimize generated Verilog parts and check syntax, lint, and behavior.
metadata:
  hermes:
    category: chip-design/rtl-enhancement
    tags: [rtl_enhancement, rtl_enhancement_verilog_optimization]
---

# Verilog Optimization

## When to Use
Use this skill when the user request matches: Use after RTL partitioning to optimize generated Verilog parts and check syntax, lint, and behavior.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Run synthesis-oriented cleanup with explicit constraints.
   - Check syntax and warnings before merging.
   - Compare simulation behavior against the original intent.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_yosys`
- `cktclaw_chip_run_iverilog`
- `cktclaw_chip_run_vvp`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
