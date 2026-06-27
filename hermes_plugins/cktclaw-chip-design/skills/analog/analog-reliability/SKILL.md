---
name: analog-reliability
description: Use for aging, EM/IR, safe operating area, ESD assumptions, and stress review.
metadata:
  hermes:
    category: chip-design/analog
    tags: [analog, analog_reliability]
---

# Analog Reliability

## When to Use
Use this skill when the user request matches: Use for aging, EM/IR, safe operating area, ESD assumptions, and stress review.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Identify stress conditions and long-duration modes.
   - Check current density, voltage limits, temperature, and device region margins.
   - List residual reliability risks and required signoff tools.
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
