# RTL Rules

- Use synthesizable SystemVerilog accepted by Icarus Verilog and Yosys.
- Prefer a single `clk` and active-low `rst_n` for V1 examples.
- Keep testbench-only code out of RTL.
- Make protocol behavior explicit through ready/valid, start/done, or bus
  handshakes.
- Avoid inferred latches, unsized arithmetic surprises, and simulation-only
  delays in RTL.
- Parameterize common widths but keep generated V1 defaults small enough for
  open-source synthesis.
