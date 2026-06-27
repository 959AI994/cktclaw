---
name: digital-dft
description: Use for scan, test access, ATPG readiness, boundary scan planning, and DFT signoff.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_dft]
---

# Digital DFT

## When to Use
Use this skill when the user request matches: Use for scan, test access, ATPG readiness, boundary scan planning, and DFT signoff.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Define controllability and observability goals.
   - Plan scan insertion, test clocks, resets, and modes.
   - Verify that DFT constraints do not break functional timing intent.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_flow_plan`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
