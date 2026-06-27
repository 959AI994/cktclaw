---
name: analog-circuit-design
description: Use for topology choice, biasing, device sizing, schematic review, and pre-layout readiness.
metadata:
  hermes:
    category: chip-design/analog
    tags: [analog, analog_circuit_design]
---

# Analog Circuit Design

## When to Use
Use this skill when the user request matches: Use for topology choice, biasing, device sizing, schematic review, and pre-layout readiness.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Choose topology from spec and PDK constraints.
   - Compute first-pass bias currents, device sizes, and operating regions.
   - Prepare simulation decks that measure the actual acceptance metrics.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_ngspice`
- `cktclaw_chip_run_xyce`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
