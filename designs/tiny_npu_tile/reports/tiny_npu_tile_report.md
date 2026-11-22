# Tiny NPU Tile RTL Delivery Report

Status: **PASS**
Project: `/home/wjx/pythonproject/cktclaw/designs/tiny_npu_tile`

## What Was Built

- 16x16 signed int8 matrix-vector MAC tile.
- 16 int32 output accumulators with programmable bias.
- Self-checking SystemVerilog testbench with waveform dump.
- Yosys gate-level structural netlist and JSON netlist.
- Tiny handwritten-digit classifier demo using 4x4 digit prototypes.

## Stage Results

- `spec_plan`: PASS - Defines a 16-input by 16-output signed int8 MAC tile with int32 accumulators.
- `rtl_generation`: PASS - Generated 4 source/script files.
- `simulation`: PASS - Icarus Verilog regression passed; VCD waveform emitted.
- `synthesis_qor`: PASS - Yosys produced generic gate-level netlist with 186676 cells.
- `signoff_gate`: PASS - RTL compiles, self-checking regression passes, VCD is emitted, and Yosys netlist/QoR are available.

## QoR Snapshot

```json
{
  "tool": "yosys",
  "technology": "generic_cmos_proxy",
  "max_frequency_mhz": null,
  "power_mw": null,
  "note": "Frequency and power need a liberty/timing/power flow; cell counts are structural proxies.",
  "num_wires": 52906,
  "num_wire_bits": 468538,
  "num_public_wires": 11,
  "num_public_wire_bits": 3269,
  "num_cells": 186676,
  "cell_types": {
    "$_AND_": 90227,
    "$_DFFE_PN0P_": 512,
    "$_DFF_PN0_": 1,
    "$_NOT_": 128,
    "$_OR_": 37645,
    "$_XOR_": 58163
  }
}
```

## Signoff Interpretation

This run reaches an open-source pre-synthesis readiness gate: RTL compile, self-checking simulation, waveform availability, and generic Yosys synthesis. For enterprise signoff, connect a liberty file plus OpenSTA/OpenROAD to replace proxy cell counts with real area, timing, and power.

## Artifacts

- `/home/wjx/pythonproject/cktclaw/designs/tiny_npu_tile/README.md`
- `/home/wjx/pythonproject/cktclaw/designs/tiny_npu_tile/build/tiny_npu_tile_tb.vvp`
- `/home/wjx/pythonproject/cktclaw/designs/tiny_npu_tile/reports/simulation.log`
- `/home/wjx/pythonproject/cktclaw/designs/tiny_npu_tile/reports/yosys.log`
- `/home/wjx/pythonproject/cktclaw/designs/tiny_npu_tile/rtl/tiny_npu_tile_16x16.sv`
- `/home/wjx/pythonproject/cktclaw/designs/tiny_npu_tile/scripts/synth_yosys.ys`
- `/home/wjx/pythonproject/cktclaw/designs/tiny_npu_tile/synth/tiny_npu_tile_16x16.json`
- `/home/wjx/pythonproject/cktclaw/designs/tiny_npu_tile/synth/tiny_npu_tile_16x16_netlist.v`
- `/home/wjx/pythonproject/cktclaw/designs/tiny_npu_tile/tb/tiny_npu_tile_tb.sv`
- `/home/wjx/pythonproject/cktclaw/designs/tiny_npu_tile/wave/tiny_npu_tile.vcd`
