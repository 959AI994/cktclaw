---
name: analog-chip-design
description: Use for analog, mixed-signal, and RF circuit design from topology to simulation, layout, extraction, and signoff.
metadata:
  hermes:
    category: chip-design/core
    tags: [core, analog_chip_design]
---

# Analog Chip Design

## When to Use
Use this skill when the user request matches: Use for analog, mixed-signal, and RF circuit design from topology to simulation, layout, extraction, and signoff.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Start with operating point, small-signal, transient, noise, and corner goals.
   - Keep PDK, device model, and measurement decks explicit.
   - Gate layout with DRC, LVS, extraction, and post-layout measurements.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_flow_plan`
- `cktclaw_chip_spec_template`
- `cktclaw_chip_run_ngspice`
- `cktclaw_chip_run_xyce`
- `cktclaw_chip_run_magic`
- `cktclaw_chip_run_netgen`
- `cktclaw_chip_run_klayout`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
