---
name: digital-rtl-design
description: Use for SystemVerilog RTL module planning, coding, lint readiness, CDC/RDC awareness, and synthesis sanity checks.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_rtl_design]
---

# Digital RTL Design

## When to Use
Use this skill when the user request matches: Use for SystemVerilog RTL module planning, coding, lint readiness, CDC/RDC awareness, and synthesis sanity checks.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Define module boundary and reset/clock policy first.
   - Write synthesizable RTL with explicit widths and stable interfaces.
   - Run compile, lint, simulation, and synthesis checks before handoff.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_iverilog`
- `cktclaw_chip_run_verilator`
- `cktclaw_chip_run_yosys`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
