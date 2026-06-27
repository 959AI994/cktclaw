---
name: digital-chip-design
description: Use for end-to-end digital chip design from specification to RTL, verification, synthesis, timing, and signoff.
metadata:
  hermes:
    category: chip-design/core
    tags: [core, digital_chip_design]
---

# Digital Chip Design

## When to Use
Use this skill when the user request matches: Use for end-to-end digital chip design from specification to RTL, verification, synthesis, timing, and signoff.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Define spec, interface, clock/reset, and PPA targets.
   - Plan architecture before writing RTL.
   - Use simulation, lint, synthesis, and timing evidence before signoff.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_flow_plan`
- `cktclaw_chip_spec_template`
- `cktclaw_chip_run_yosys`
- `cktclaw_chip_run_iverilog`
- `cktclaw_chip_run_verilator`
- `cktclaw_chip_run_opensta`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
