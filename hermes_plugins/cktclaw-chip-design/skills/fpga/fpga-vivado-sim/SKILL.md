---
name: fpga-vivado-sim
description: Use for Vivado simulation planning, compile order, wave debug, and testbench execution.
metadata:
  hermes:
    category: chip-design/fpga
    tags: [fpga, fpga_vivado_sim]
---

# Vivado Simulation

## When to Use
Use this skill when the user request matches: Use for Vivado simulation planning, compile order, wave debug, and testbench execution.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Compile design and testbench with stable libraries.
   - Use self-checking pass/fail conditions.
   - Save waveforms only when they answer a debug question.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_iverilog`
- `cktclaw_chip_run_verilator`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
