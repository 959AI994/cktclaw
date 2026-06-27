---
name: analog-ams-integration
description: Use for mixed-signal boundary planning, supplies, clocks, resets, converters, and top-level contracts.
metadata:
  hermes:
    category: chip-design/analog
    tags: [analog, analog_ams_integration]
---

# Analog AMS Integration

## When to Use
Use this skill when the user request matches: Use for mixed-signal boundary planning, supplies, clocks, resets, converters, and top-level contracts.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Define analog/digital boundaries and signal ownership.
   - Specify level shifting, sampling clocks, references, and calibration paths.
   - Plan integration tests that observe both analog metrics and digital behavior.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_flow_plan`
- `cktclaw_chip_run_ngspice`
- `cktclaw_chip_run_verilator`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
