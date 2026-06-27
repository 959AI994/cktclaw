---
name: fpga-vivado-tcl
description: Use for Vivado Tcl project and non-project mode automation.
metadata:
  hermes:
    category: chip-design/fpga
    tags: [fpga, fpga_vivado_tcl]
---

# Vivado Tcl

## When to Use
Use this skill when the user request matches: Use for Vivado Tcl project and non-project mode automation.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Prefer reproducible Tcl over manual GUI steps.
   - Record project part, source set, constraints, and report commands.
   - Keep paths relative when possible.
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
