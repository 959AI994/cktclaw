---
name: digital-eda-closure
description: Use for digital RTL tasks that require actual compile, simulation PASS evidence, Yosys synthesis, netlist generation, QoR reports, artifact paths, and repeated failure triage until all requested gates pass.
metadata:
  hermes:
    category: chip-design/digital
    tags: [digital, eda_closure, rtl, simulation, synthesis, qor]
---

# Digital EDA Closure

## Procedure
1. Start by calling `cktclaw_chip_flow_plan` with the full user request. Follow the recommended skills, tools, stages, and acceptance gates.
2. Create a compact project directory with `rtl/`, `scripts/`, and `outputs/`.
3. Write a runnable spec contract in comments or a short markdown file before coding:
   - top module name, ports, reset behavior, address map, data widths, signedness
   - self-checking test goal and expected PASS token
   - synthesis outputs and QoR report names
4. Generate RTL and testbench together. The testbench must be self-checking and must fail loudly when the requested behavior is not met.
5. Run the gates in order and save logs:
   - compile: `iverilog -g2012 ... 2>&1 | tee outputs/compile.log`
   - simulate: `vvp outputs/<sim_binary> 2>&1 | tee outputs/sim.log`
   - synthesize: `yosys -s scripts/<script>.ys 2>&1 | tee outputs/yosys.log`
   - report: write synthesized netlist, JSON if useful, and QoR report
6. After each run, call `cktclaw_chip_closure_check` on the project directory. Do not give a final answer until it reports all required gates as PASS.

## Debug Rules
- Fix the earliest failing gate first. Do not change later stages until compile and simulation are stable.
- Preserve the user's requested behavior. Do not change labels, expected outputs, stimuli, or task scope merely to make a test pass.
- For classification tests, first inspect byte packing, register read latency, signedness, row and column mapping, and argmax scoreboard logic.
- For synchronous register reads, sample read data after the clock edge that updates `rd_data`.
- For Yosys QoR, prefer portable commands such as `synth -top <top>`, `tee -o outputs/<name>.rpt stat -width`, `write_verilog`, and `write_json`.
- Treat generated files as untrusted until compile, simulation, synthesis, netlist, and QoR evidence exist.

## Evidence To Return
- List the exact commands that were run.
- Cite the RTL, testbench, synthesis script, simulation log, Yosys log, netlist, and QoR report paths.
- Include the PASS token and a small QoR summary from the report.
- If any gate remains failing, return the failing gate, log path, root cause, and next action instead of claiming success.
