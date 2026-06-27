---
name: rtl-enhancement-chip-autodesign
description: Use for generating and validating small RTL/IP blocks with simulation, synthesis, and repair evidence.
metadata:
  hermes:
    category: chip-design/rtl-enhancement
    tags: [rtl_enhancement, rtl_enhancement_chip_autodesign]
---

# RTL Enhancement Chip Autodesign

## When to Use
Use this skill when the user request matches: Use for generating and validating small RTL/IP blocks with simulation, synthesis, and repair evidence.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Start from a precise spec template.
   - Generate RTL and a self-checking testbench.
   - Gate results with simulation and synthesis summaries.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_spec_template`
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
