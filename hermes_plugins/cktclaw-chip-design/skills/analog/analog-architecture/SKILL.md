---
name: analog-architecture
description: Use for analog/RF/AMS architecture choices, block partitioning, budgets, and feasibility review.
metadata:
  hermes:
    category: chip-design/analog
    tags: [analog, analog_architecture]
---

# Analog Architecture

## When to Use
Use this skill when the user request matches: Use for analog/RF/AMS architecture choices, block partitioning, budgets, and feasibility review.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Translate system targets into block-level budgets.
   - Account for gain, noise, bandwidth, linearity, power, area, supply, and process.
   - Document tradeoffs and measurement decks before circuit sizing.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_flow_plan`
- `cktclaw_chip_spec_template`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
