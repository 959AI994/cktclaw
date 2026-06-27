---
name: digital-infrastructure
description: Use for digital EDA tool detection, environment setup, wrappers, MCP snippets, and reproducibility checks.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_infrastructure]
---

# Digital Infrastructure

## When to Use
Use this skill when the user request matches: Use for digital EDA tool detection, environment setup, wrappers, MCP snippets, and reproducibility checks.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Run doctor before execution.
   - Install or locate tools with explicit root paths.
   - Generate MCP config only for tools the agent should see.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_install_toolchain`
- `cktclaw_chip_doctor`
- `cktclaw_chip_generate_mcp_config`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
