---
name: digital-formal-verification
description: Use for property checks, bounded proofs, equivalence checks, and counterexample triage.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_formal_verification]
---

# Digital Formal Verification

## When to Use
Use this skill when the user request matches: Use for property checks, bounded proofs, equivalence checks, and counterexample triage.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - State assumptions and guarantees before running proofs.
   - Bind properties to stable RTL interfaces.
   - Treat counterexamples as debug artifacts and minimize them.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_sby`
- `cktclaw_chip_run_yosys`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
