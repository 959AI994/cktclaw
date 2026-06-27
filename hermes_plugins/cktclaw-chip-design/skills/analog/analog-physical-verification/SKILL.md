---
name: analog-physical-verification
description: Use for DRC, LVS, antenna, density, and physical rule debug.
metadata:
  hermes:
    category: chip-design/analog
    tags: [analog, analog_physical_verification]
---

# Analog Physical Verification

## When to Use
Use this skill when the user request matches: Use for DRC, LVS, antenna, density, and physical rule debug.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Run DRC before LVS.
   - Use a known-good schematic or source netlist for LVS.
   - Group violations by rule, location, and design intent.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_magic`
- `cktclaw_chip_run_klayout`
- `cktclaw_chip_run_netgen`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
