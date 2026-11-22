# Chip AutoDesign

Use this skill for end-to-end RTL IP delivery from natural-language intent.

The flow must always produce:

- `spec.md` with module goal, interface, protocol, clock/reset, parameters,
  verification requirements, PPA targets, and non-goals.
- `plan.md` with executable stages, tools, file layout, acceptance gates, risks,
  and fallback strategy.
- RTL, self-checking testbench, simulation log, waveform, coverage gap report,
  Yosys netlist/QoR, and final delivery report.

Default V1 scope is single-clock RTL IP: FIFO, AXI-lite register block, DSP MAC,
and Tiny NPU tile regression examples. Do not claim full SoC, physical design,
or signoff power/timing unless a real downstream flow is attached.

Default execution policy:

1. Draft spec and plan.
2. Ask for one confirmation unless `--yes` is provided or stdin is non-interactive.
3. Execute RTL/testbench/simulation/coverage/QoR/signoff to completion.
4. On compile, simulation, or synthesis failure, emit a structured FixRequest and
   loop back up to the configured iteration limit.
