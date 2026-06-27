---
name: analog-post-layout-signoff
description: Use for extracted simulation, corners, Monte Carlo, final measurements, and signoff packages.
metadata:
  hermes:
    category: chip-design/analog
    tags: [analog, analog_post_layout_signoff]
---

# Analog Post Layout Signoff

## When to Use
Use this skill when the user request matches: Use for extracted simulation, corners, Monte Carlo, final measurements, and signoff packages.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Use extracted netlists and final PDK models.
   - Run required PVT corners and mismatch/yield checks.
   - Summarize deltas versus pre-layout and spec margin.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_ngspice`
- `cktclaw_chip_run_xyce`
- `cktclaw_chip_run_netgen`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
