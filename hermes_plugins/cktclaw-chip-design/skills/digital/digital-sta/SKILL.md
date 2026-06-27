---
name: digital-sta
description: Use for static timing analysis, SDC review, path triage, and timing signoff preparation.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_sta]
---

# Digital STA

## When to Use
Use this skill when the user request matches: Use for static timing analysis, SDC review, path triage, and timing signoff preparation.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Check clocks, generated clocks, IO delays, false paths, and multicycle paths.
   - Load liberty, netlist, constraints, and parasitics when available.
   - Report WNS, TNS, worst paths, unconstrained paths, and next fixes.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_opensta`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
