---
name: digital-logic-synthesis
description: Use for Yosys or OpenLane synthesis, netlist generation, QoR extraction, and synthesis issue triage.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_logic_synthesis]
---

# Digital Logic Synthesis

## When to Use
Use this skill when the user request matches: Use for Yosys or OpenLane synthesis, netlist generation, QoR extraction, and synthesis issue triage.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Confirm top module, constraints, libraries, and target process.
   - Run synthesis with reproducible scripts.
   - Use portable Yosys report commands such as `tee -o <report>.rpt stat -width` unless a real liberty file is available.
   - Review unmapped cells, warnings, area, levels, and generated netlists.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_yosys`
- `cktclaw_chip_run_openlane2`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
