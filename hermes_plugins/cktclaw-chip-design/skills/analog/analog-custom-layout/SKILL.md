---
name: analog-custom-layout
description: Use for analog custom layout planning, matching, shielding, guard rings, and layout handoff.
metadata:
  hermes:
    category: chip-design/analog
    tags: [analog, analog_custom_layout]
---

# Analog Custom Layout

## When to Use
Use this skill when the user request matches: Use for analog custom layout planning, matching, shielding, guard rings, and layout handoff.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Identify matched pairs, sensitive nodes, current paths, and symmetry constraints.
   - Plan guard rings, shielding, dummies, and routing hierarchy.
   - Keep layout decisions tied to extracted simulation risk.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_magic`
- `cktclaw_chip_run_klayout`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
