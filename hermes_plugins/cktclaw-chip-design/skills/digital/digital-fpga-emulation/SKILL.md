---
name: digital-fpga-emulation
description: Use for FPGA prototyping, emulation planning, constraints, synthesis, implementation, and board bring-up.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_fpga_emulation]
---

# Digital FPGA Emulation

## When to Use
Use this skill when the user request matches: Use for FPGA prototyping, emulation planning, constraints, synthesis, implementation, and board bring-up.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Map clocks, pins, resets, memories, and debug probes.
   - Create constraints before implementation.
   - Use timing, resource, and board smoke evidence for handoff.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_yosys`
- `cktclaw_chip_run_verilator`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
