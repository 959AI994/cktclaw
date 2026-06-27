---
name: rtl-enhancement-rtl-spec-analyzer
description: Use to compare RTL against a written specification and map features to ports and signals.
metadata:
  hermes:
    category: chip-design/rtl-enhancement
    tags: [rtl_enhancement, rtl_enhancement_rtl_spec_analyzer]
---

# RTL Spec Analyzer

## When to Use
Use this skill when the user request matches: Use to compare RTL against a written specification and map features to ports and signals.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Parse ports, parameters, clocks, resets, and visible state.
   - Extract specification features and expected pin behavior.
   - Report mismatches, ambiguities, and missing observability.
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
