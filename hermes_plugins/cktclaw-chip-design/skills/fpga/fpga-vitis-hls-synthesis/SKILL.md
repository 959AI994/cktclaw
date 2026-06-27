---
name: fpga-vitis-hls-synthesis
description: Use for Vitis HLS kernel synthesis, pragmas, interfaces, reports, and cosimulation.
metadata:
  hermes:
    category: chip-design/fpga
    tags: [fpga, fpga_vitis_hls_synthesis]
---

# Vitis HLS Synthesis

## When to Use
Use this skill when the user request matches: Use for Vitis HLS kernel synthesis, pragmas, interfaces, reports, and cosimulation.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Define C/C++ top function and interface pragmas.
   - Run C simulation before synthesis when possible.
   - Review latency, initiation interval, resources, and generated RTL ports.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_bambu`
- `cktclaw_chip_run_verilator`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
