---
name: analog-em-modeling
description: Use for EM-sensitive inductors, transformers, packages, antennas, and RF structures.
metadata:
  hermes:
    category: chip-design/analog
    tags: [analog, analog_em_modeling]
---

# Analog EM Modeling

## When to Use
Use this skill when the user request matches: Use for EM-sensitive inductors, transformers, packages, antennas, and RF structures.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Define geometry, ports, materials, mesh, and boundary conditions.
   - Run bounded EM solves for targeted structures.
   - Feed extracted parameters back into circuit simulation.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_openems`
- `cktclaw_chip_run_klayout`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
