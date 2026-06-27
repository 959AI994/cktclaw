---
name: digital-physical-design
description: Use for floorplan, placement, CTS, routing, OpenROAD/OpenLane2 flow review, and physical signoff preparation.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_physical_design]
---

# Digital Physical Design

## When to Use
Use this skill when the user request matches: Use for floorplan, placement, CTS, routing, OpenROAD/OpenLane2 flow review, and physical signoff preparation.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Confirm PDK, floorplan constraints, utilization, macro placement, clocks, and power intent.
   - Run stages with preserved logs and reports.
   - Review timing, congestion, DRC, power, area, and failing stage root cause.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_openroad`
- `cktclaw_chip_run_openlane2`
- `cktclaw_chip_run_klayout`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
