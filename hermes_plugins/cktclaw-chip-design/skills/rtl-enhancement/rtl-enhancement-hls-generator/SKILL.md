---
name: rtl-enhancement-hls-generator
description: Use for HLS C/C++ kernel generation, pragmas, interface review, and generated RTL validation.
metadata:
  hermes:
    category: chip-design/rtl-enhancement
    tags: [rtl_enhancement, rtl_enhancement_hls_generator]
---

# HLS Generator

## When to Use
Use this skill when the user request matches: Use for HLS C/C++ kernel generation, pragmas, interface review, and generated RTL validation.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Define algorithm, data movement, and latency/throughput target.
   - Apply HLS directives intentionally and record them.
   - Validate C simulation, synthesis report, and generated RTL interface.
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
