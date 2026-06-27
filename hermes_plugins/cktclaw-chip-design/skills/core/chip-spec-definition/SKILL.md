---
name: chip-spec-definition
description: Use to turn a chip or IP idea into a precise implementation-ready design specification.
metadata:
  hermes:
    category: chip-design/core
    tags: [core, chip_spec_definition]
---

# Chip Spec Definition

## When to Use
Use this skill when the user request matches: Use to turn a chip or IP idea into a precise implementation-ready design specification.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Capture intent, interfaces, constraints, artifacts, and acceptance gates.
   - Separate non-goals from hard requirements.
   - Record exact tool, PDK, board, or simulator assumptions.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_spec_template`
- `cktclaw_chip_flow_plan`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
