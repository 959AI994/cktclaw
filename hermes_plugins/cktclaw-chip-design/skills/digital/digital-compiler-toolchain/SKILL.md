---
name: digital-compiler-toolchain
description: Use for ISA, ABI, assembler, linker, runtime library, and compiler backend planning.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_compiler_toolchain]
---

# Digital Compiler Toolchain

## When to Use
Use this skill when the user request matches: Use for ISA, ABI, assembler, linker, runtime library, and compiler backend planning.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Define ISA features, calling convention, memory model, and startup path.
   - Test assembler/linker output against RTL or architectural models.
   - Keep toolchain validation tied to real firmware workloads.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_gem5`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
