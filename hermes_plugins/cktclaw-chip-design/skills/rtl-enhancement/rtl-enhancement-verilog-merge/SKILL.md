---
name: rtl-enhancement-verilog-merge
description: Use to merge optimized Verilog parts back into a complete RTL module and verify equivalence intent.
metadata:
  hermes:
    category: chip-design/rtl-enhancement
    tags: [rtl_enhancement, rtl_enhancement_verilog_merge]
---

# Verilog Merge

## When to Use
Use this skill when the user request matches: Use to merge optimized Verilog parts back into a complete RTL module and verify equivalence intent.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Preserve top-level module name and public ports.
   - Resolve internal signal ownership and parameter propagation.
   - Run compile and self-checking simulation after merge.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_iverilog`
- `cktclaw_chip_run_vvp`
- `cktclaw_chip_run_yosys`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
