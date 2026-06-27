---
name: analog-rf-design
description: Use for RF blocks, matching networks, S-parameters, noise figure, linearity, and EM-aware review.
metadata:
  hermes:
    category: chip-design/analog
    tags: [analog, analog_rf_design]
---

# Analog RF Design

## When to Use
Use this skill when the user request matches: Use for RF blocks, matching networks, S-parameters, noise figure, linearity, and EM-aware review.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - State frequency bands, impedance, gain, NF, IIP3, P1dB, and power targets.
   - Separate circuit simulation from EM or package assumptions.
   - Verify matching, stability, and layout-sensitive structures.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_ngspice`
- `cktclaw_chip_run_openems`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
