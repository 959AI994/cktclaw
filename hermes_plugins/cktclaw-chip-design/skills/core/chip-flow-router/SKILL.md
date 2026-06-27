---
name: chip-flow-router
description: Use to choose the right chip design skill family and EDA tools for a request.
metadata:
  hermes:
    category: chip-design/core
    tags: [core, chip_flow_router]
---

# Chip Flow Router

## When to Use
Use this skill when the user request matches: Use to choose the right chip design skill family and EDA tools for a request.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Classify the task as digital, analog, AMS, RF, FPGA, HLS, or SoC.
   - For digital tasks requiring RTL compile, simulation PASS, synthesis, netlist, or QoR evidence, select `digital-eda-closure` first.
   - Choose the smallest flow that can produce evidence.
   - Escalate only when artifacts or targets require more stages.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_flow_plan`
- `cktclaw_chip_doctor`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
