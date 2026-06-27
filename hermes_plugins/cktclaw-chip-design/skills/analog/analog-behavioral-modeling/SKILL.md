---
name: analog-behavioral-modeling
description: Use for Verilog-A, real-number, and abstract analog models for faster verification.
metadata:
  hermes:
    category: chip-design/analog
    tags: [analog, analog_behavioral_modeling]
---

# Analog Behavioral Modeling

## When to Use
Use this skill when the user request matches: Use for Verilog-A, real-number, and abstract analog models for faster verification.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Define model intent, validity range, and non-modeled effects.
   - Fit behavior to measured or simulated reference data.
   - Validate model outputs against golden decks before integration.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_openvaf`
- `cktclaw_chip_run_ngspice`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
