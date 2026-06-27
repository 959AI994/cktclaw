---
name: digital-hls
description: Use for high-level synthesis from C/C++ kernels, pragmas, scheduling, interfaces, and RTL handoff.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_hls]
---

# Digital HLS

## When to Use
Use this skill when the user request matches: Use for high-level synthesis from C/C++ kernels, pragmas, scheduling, interfaces, and RTL handoff.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Freeze algorithm, data types, memory interfaces, and throughput target.
   - Choose pragmas for pipeline, unroll, dataflow, and memory partitioning.
   - Compare generated RTL latency, area, and interface behavior.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_bambu`
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
