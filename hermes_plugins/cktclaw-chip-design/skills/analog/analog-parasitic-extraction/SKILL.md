---
name: analog-parasitic-extraction
description: Use for extracting parasitics and preparing post-layout netlists.
metadata:
  hermes:
    category: chip-design/analog
    tags: [analog, analog_parasitic_extraction]
---

# Analog Parasitic Extraction

## When to Use
Use this skill when the user request matches: Use for extracting parasitics and preparing post-layout netlists.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Confirm layout, PDK tech files, and extraction mode.
   - Generate extracted netlist with stable naming.
   - Compare pre-layout and post-layout measurements.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_magic`
- `cktclaw_chip_run_netgen`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
