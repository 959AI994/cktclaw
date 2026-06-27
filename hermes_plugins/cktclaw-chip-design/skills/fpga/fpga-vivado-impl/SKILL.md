---
name: fpga-vivado-impl
description: Use for Vivado implementation, placement, routing, timing closure, and bitstream handoff.
metadata:
  hermes:
    category: chip-design/fpga
    tags: [fpga, fpga_vivado_impl]
---

# Vivado Implementation

## When to Use
Use this skill when the user request matches: Use for Vivado implementation, placement, routing, timing closure, and bitstream handoff.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Check constraints before implementation.
   - Review placement, routing, utilization, timing, and DRC reports.
   - Document any unconstrained or waived paths.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_flow_plan`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
