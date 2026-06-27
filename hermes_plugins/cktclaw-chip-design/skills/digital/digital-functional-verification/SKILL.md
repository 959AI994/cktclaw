---
name: digital-functional-verification
description: Use for testbench strategy, assertions, stimulus, scoreboards, regressions, and coverage closure.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_functional_verification]
---

# Digital Functional Verification

## When to Use
Use this skill when the user request matches: Use for testbench strategy, assertions, stimulus, scoreboards, regressions, and coverage closure.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Create a verification plan from features and failure modes.
   - Build self-checking tests and assertions.
   - Keep expected results tied to the requested behavior; do not edit labels or stimuli only to make a failing run pass.
   - For synchronous register reads, sample after the clock edge that updates the read data.
   - Report pass/fail evidence, coverage gaps, and seed or vector details.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_iverilog`
- `cktclaw_chip_run_vvp`
- `cktclaw_chip_run_verilator`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
