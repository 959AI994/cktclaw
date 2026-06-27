---
name: rtl-enhancement-verilog-generator
description: Use for high-quality RTL generation with strict compile, lint, simulation, and synthesis evidence.
metadata:
  hermes:
    category: chip-design/rtl-enhancement
    tags: [rtl_enhancement, rtl_enhancement_verilog_generator]
---

# Verilog Generator

## When to Use
Use this skill when the user request matches: Use for high-quality RTL generation with strict compile, lint, simulation, and synthesis evidence.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Use the spec template and define acceptance tests first.
   - Generate RTL with explicit reset, width, and handshake rules.
   - Do not sign off without at least one local compile or synthesis check.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_spec_template`
- `cktclaw_chip_run_iverilog`
- `cktclaw_chip_run_yosys`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
