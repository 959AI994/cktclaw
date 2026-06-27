---
name: digital-embedded-firmware
description: Use for boot code, drivers, firmware tests, linker scripts, and hardware-software bring-up.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, digital_embedded_firmware]
---

# Digital Embedded Firmware

## When to Use
Use this skill when the user request matches: Use for boot code, drivers, firmware tests, linker scripts, and hardware-software bring-up.

## Procedure
1. Scope the deliverable, required inputs, and acceptance gates.
2. Apply these domain rules:
   - Identify reset vector, memory map, peripherals, and ABI.
   - Keep firmware tests small and tied to visible hardware effects.
   - Record build command, binary, logs, and pass/fail criteria.
3. Select the smallest tool set that can produce useful evidence.
4. Save or cite generated artifacts, commands, reports, and remaining risks.

## Recommended Tools
- `cktclaw_chip_run_gem5`
- `cktclaw_chip_run_verilator`

## Verification
- Confirm that required inputs and assumptions are explicit.
- Run at least one compile, simulation, synthesis, measurement, or report check when the needed tool exists.
- Return pass/fail evidence with command names, artifacts, metrics, and unresolved issues.

## Pitfalls
- Do not skip the spec or interface contract.
- Do not treat a generated file as signed off without tool evidence.
- Do not install or invoke proprietary tools automatically; only detect and document them.
