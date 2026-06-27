---
name: fpga-vivado-debug
description: Use for ILA/VIO debug, hardware bring-up, trigger planning, and failure localization.
metadata:
  hermes:
    category: chip-design/fpga
    tags: [fpga, fpga_vivado_debug]
---

# Vivado Debug

## When to Use
Use this skill when the user request matches: Use for ILA/VIO debug, hardware bring-up, trigger planning, and failure localization.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Choose probes that answer a specific hypothesis.
   - Keep trigger conditions small and reproducible.
   - Relate captured waveforms to expected protocol states.
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
