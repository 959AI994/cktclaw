---
name: digital-soc-integration
description: Use for SoC IP integration, bus maps, address maps, clock/reset domains, and top-level verification.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_soc_integration]
---

# Digital SoC Integration

## When to Use
Use this skill when the user request matches: Use for SoC IP integration, bus maps, address maps, clock/reset domains, and top-level verification.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Inventory IP, bus protocols, interrupts, DMA, memory map, and firmware contract.
   - Check clock/reset crossings and register visibility.
   - Build smoke tests that exercise integration paths.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_flow_plan`
- `cktclaw_chip_run_verilator`
- `cktclaw_chip_run_yosys`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
