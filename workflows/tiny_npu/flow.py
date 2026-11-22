"""Deterministic RTL-to-QoR flow for a 16x16 Tiny NPU Tile.

The flow is intentionally local and tool-driven: it generates a small but real
SystemVerilog design, builds a self-checking testbench, runs Icarus Verilog,
emits a VCD waveform, synthesizes with Yosys, and writes a delivery report.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TinyNPUFlowResult:
    status: str
    project_dir: str
    stages: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)
    qor: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TinyNPUFlow:
    """Create and verify a tiny 16x16 matrix-vector NPU tile project."""

    def __init__(
        self,
        project_dir: str | Path = "designs/tiny_npu_tile",
        *,
        force: bool = False,
    ) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.force = force
        self.rtl_dir = self.project_dir / "rtl"
        self.tb_dir = self.project_dir / "tb"
        self.scripts_dir = self.project_dir / "scripts"
        self.build_dir = self.project_dir / "build"
        self.wave_dir = self.project_dir / "wave"
        self.synth_dir = self.project_dir / "synth"
        self.reports_dir = self.project_dir / "reports"

    async def run(self) -> TinyNPUFlowResult:
        stages: Dict[str, Dict[str, Any]] = {}
        artifacts: List[str] = []

        stages["spec_plan"] = self._stage_ok(
            "Defines a 16-input by 16-output signed int8 MAC tile with int32 accumulators."
        )

        self._prepare_dirs()
        written = self._write_sources()
        artifacts.extend(str(p) for p in written)
        stages["rtl_generation"] = self._stage_ok(
            f"Generated {len(written)} source/script files."
        )

        sim = await self._run_simulation()
        stages["simulation"] = sim
        artifacts.extend(sim.get("artifacts", []))

        synth = await self._run_synthesis()
        stages["synthesis_qor"] = synth
        artifacts.extend(synth.get("artifacts", []))

        qor = synth.get("qor", {})
        status = "PASS" if sim["status"] == "PASS" and synth["status"] == "PASS" else "FAIL"
        if status == "PASS":
            stages["signoff_gate"] = self._stage_ok(
                "RTL compiles, self-checking regression passes, VCD is emitted, and Yosys netlist/QoR are available."
            )
        else:
            stages["signoff_gate"] = {
                "status": "FAIL",
                "issues": ["At least one required RTL readiness gate failed."],
            }

        result = TinyNPUFlowResult(
            status=status,
            project_dir=str(self.project_dir),
            stages=stages,
            artifacts=sorted(set(artifacts)),
            qor=qor,
        )
        result.summary = self._write_report(result)
        result.artifacts.append(str(self.reports_dir / "tiny_npu_tile_report.md"))
        return result

    @staticmethod
    def _stage_ok(summary: str, **extra: Any) -> Dict[str, Any]:
        data = {"status": "PASS", "summary": summary}
        data.update(extra)
        return data

    def _prepare_dirs(self) -> None:
        if self.project_dir.exists() and self.force:
            for child in self.project_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        for d in (
            self.rtl_dir,
            self.tb_dir,
            self.scripts_dir,
            self.build_dir,
            self.wave_dir,
            self.synth_dir,
            self.reports_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def _write_sources(self) -> List[Path]:
        files = {
            self.rtl_dir / "tiny_npu_tile_16x16.sv": _RTL,
            self.tb_dir / "tiny_npu_tile_tb.sv": _TB,
            self.scripts_dir / "synth_yosys.ys": _YOSYS_SCRIPT,
            self.project_dir / "README.md": _README,
        }
        for path, text in files.items():
            path.write_text(text, encoding="utf-8")
        return list(files.keys())

    async def _run_simulation(self) -> Dict[str, Any]:
        iverilog = shutil.which("iverilog")
        vvp = shutil.which("vvp")
        if not iverilog or not vvp:
            return {
                "status": "FAIL",
                "issues": ["iverilog/vvp not found; install Icarus Verilog."],
            }

        out = self.build_dir / "tiny_npu_tile_tb.vvp"
        compile_cmd = [
            iverilog,
            "-g2012",
            "-Wall",
            "-o",
            str(out),
            str(self.rtl_dir / "tiny_npu_tile_16x16.sv"),
            str(self.tb_dir / "tiny_npu_tile_tb.sv"),
        ]
        compile_result = await _run_cmd(compile_cmd, cwd=self.project_dir, timeout=120)
        if compile_result["returncode"] != 0:
            return {
                "status": "FAIL",
                "command": compile_cmd,
                "output": compile_result["output"],
                "issues": ["Icarus compile failed."],
            }

        sim_result = await _run_cmd([vvp, str(out)], cwd=self.project_dir, timeout=120)
        transcript = self.reports_dir / "simulation.log"
        transcript.write_text(sim_result["output"], encoding="utf-8")

        digit6_passed = "PASS: digit 6 classified" in sim_result["output"]
        passed = (
            sim_result["returncode"] == 0
            and "ALL TESTS PASSED" in sim_result["output"]
            and digit6_passed
        )
        return {
            "status": "PASS" if passed else "FAIL",
            "summary": (
                "Icarus Verilog regression passed; digit_6_recognition PASS; VCD waveform emitted."
                if passed else
                "Icarus Verilog regression failed."
            ),
            "command": [compile_cmd, [vvp, str(out)]],
            "output": sim_result["output"],
            "artifacts": [
                str(transcript),
                str(self.wave_dir / "tiny_npu_tile.vcd"),
                str(out),
            ],
            "coverage": {
                "functional_tests": [
                    "zero vector",
                    "identity mapping",
                    "all-ones reduction",
                    "signed checkerboard",
                    "digit classifier 0/1/2/6/7",
                ],
                "digit_6_recognition": "PASS" if digit6_passed else "FAIL",
                "target_digit": 6,
                "known_gap": (
                    "Open-source run records functional coverage as an explicit checklist; "
                    "line/toggle coverage requires Verilator or a commercial simulator."
                ),
            },
            "issues": [] if passed else ["Simulation did not report ALL TESTS PASSED and digit_6_recognition PASS."],
        }

    async def _run_synthesis(self) -> Dict[str, Any]:
        yosys = shutil.which("yosys")
        if not yosys:
            return {
                "status": "FAIL",
                "issues": ["yosys not found; install Yosys or expose it in PATH."],
            }

        cmd = [yosys, "-s", str(self.scripts_dir / "synth_yosys.ys")]
        result = await _run_cmd(cmd, cwd=self.project_dir, timeout=180)
        log = self.reports_dir / "yosys.log"
        log.write_text(result["output"], encoding="utf-8")
        qor = _parse_yosys_qor(result["output"])
        passed = result["returncode"] == 0 and qor.get("num_cells", 0) > 0
        return {
            "status": "PASS" if passed else "FAIL",
            "summary": (
                f"Yosys produced generic gate-level netlist with {qor.get('num_cells', 0)} cells."
                if passed else
                "Yosys synthesis failed or QoR was not parseable."
            ),
            "command": cmd,
            "output": result["output"][-5000:],
            "qor": qor,
            "artifacts": [
                str(log),
                str(self.synth_dir / "tiny_npu_tile_16x16_netlist.v"),
                str(self.synth_dir / "tiny_npu_tile_16x16.json"),
            ],
            "issues": [] if passed else ["Yosys synthesis failed or produced no cells."],
        }

    def _write_report(self, result: TinyNPUFlowResult) -> str:
        report_path = self.reports_dir / "tiny_npu_tile_report.md"
        lines = [
            "# Tiny NPU Tile RTL Delivery Report",
            "",
            f"Status: **{result.status}**",
            f"Project: `{result.project_dir}`",
            "",
            "## What Was Built",
            "",
            "- 16x16 signed int8 matrix-vector MAC tile.",
            "- 16 int32 output accumulators with programmable bias.",
            "- Self-checking SystemVerilog testbench with waveform dump.",
            "- Yosys gate-level structural netlist and JSON netlist.",
            "- Tiny handwritten-digit classifier demo using 4x4 digit prototypes.",
            "- Hard signoff test for digit_6_recognition.",
            "",
            "## Stage Results",
            "",
        ]
        for name, stage in result.stages.items():
            lines.append(f"- `{name}`: {stage.get('status')} - {stage.get('summary', '')}")
            coverage = stage.get("coverage") or {}
            if coverage.get("digit_6_recognition"):
                lines.append(f"  - digit_6_recognition: **{coverage.get('digit_6_recognition')}**")
            for issue in stage.get("issues", []) or []:
                lines.append(f"  - issue: {issue}")
        lines.extend([
            "",
            "## QoR Snapshot",
            "",
            "```json",
            json.dumps(result.qor, indent=2, ensure_ascii=False),
            "```",
            "",
            "## Signoff Interpretation",
            "",
            "This run reaches an open-source pre-synthesis readiness gate: RTL compile, "
            "self-checking simulation including digit_6_recognition, waveform availability, and generic Yosys synthesis. "
            "For enterprise signoff, connect a liberty file plus OpenSTA/OpenROAD to replace "
            "proxy cell counts with real area, timing, and power.",
            "",
            "## Artifacts",
            "",
        ])
        for artifact in result.artifacts:
            lines.append(f"- `{artifact}`")
        text = "\n".join(lines) + "\n"
        report_path.write_text(text, encoding="utf-8")
        return text


async def _run_cmd(cmd: List[str], *, cwd: Path, timeout: int) -> Dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
        env=os.environ.copy(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"returncode": -1, "output": f"Timed out after {timeout}s"}
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    return {
        "returncode": proc.returncode,
        "output": "\n".join(x for x in [out, err] if x).strip(),
    }


def _parse_yosys_qor(text: str) -> Dict[str, Any]:
    qor: Dict[str, Any] = {
        "tool": "yosys",
        "technology": "generic_cmos_proxy",
        "max_frequency_mhz": None,
        "power_mw": None,
        "note": "Frequency and power need a liberty/timing/power flow; cell counts are structural proxies.",
    }
    patterns = {
        "num_wires": [r"Number of wires:\s+(\d+)", r"\n\s*(\d+)\s+wires\s*\n"],
        "num_wire_bits": [r"Number of wire bits:\s+(\d+)", r"\n\s*(\d+)\s+wire bits\s*\n"],
        "num_public_wires": [r"Number of public wires:\s+(\d+)", r"\n\s*(\d+)\s+public wires\s*\n"],
        "num_public_wire_bits": [
            r"Number of public wire bits:\s+(\d+)",
            r"\n\s*(\d+)\s+public wire bits\s*\n",
        ],
        "num_memories": [r"Number of memories:\s+(\d+)", r"\n\s*(\d+)\s+memories\s*\n"],
        "num_processes": [r"Number of processes:\s+(\d+)", r"\n\s*(\d+)\s+processes\s*\n"],
        "num_cells": [r"Number of cells:\s+(\d+)", r"\n\s*(\d+)\s+cells\s*\n"],
    }
    for key, key_patterns in patterns.items():
        for pattern in key_patterns:
            matches = re.findall(pattern, text)
            if matches:
                qor[key] = int(matches[-1])
                break

    cell_types: Dict[str, int] = {}
    in_cells = False
    for line in text.splitlines():
        if line.strip() == "Number of cells:" or re.match(r"\s*\d+\s+cells\s*$", line):
            in_cells = True
            continue
        if in_cells:
            m = re.match(r"\s+(\S+)\s+(\d+)\s*$", line)
            if not m:
                m = re.match(r"\s+(\d+)\s+(\S+)\s*$", line)
            if m:
                if m.group(1).isdigit():
                    cell_types[m.group(2)] = int(m.group(1))
                else:
                    cell_types[m.group(1)] = int(m.group(2))
            elif line.strip() == "":
                in_cells = False
    if cell_types:
        qor["cell_types"] = cell_types
    return qor


_RTL = r'''// 16x16 Tiny NPU Tile
// Computes outputs[o] = bias[o] + sum_i activations[i] * weights[o][i].
module tiny_npu_tile_16x16 #(
    parameter integer DATA_W = 8,
    parameter integer ACC_W = 32,
    parameter integer IN_DIM = 16,
    parameter integer OUT_DIM = 16
) (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic signed [DATA_W*IN_DIM-1:0] activations,
    input  logic signed [DATA_W*IN_DIM*OUT_DIM-1:0] weights,
    input  logic signed [ACC_W*OUT_DIM-1:0] bias,
    output logic done,
    output logic busy,
    output logic signed [ACC_W*OUT_DIM-1:0] outputs
);
    function automatic signed [DATA_W-1:0] get_activation(input integer idx);
        get_activation = activations[idx*DATA_W +: DATA_W];
    endfunction

    function automatic signed [DATA_W-1:0] get_weight(
        input integer out_idx,
        input integer in_idx
    );
        get_weight = weights[(out_idx*IN_DIM + in_idx)*DATA_W +: DATA_W];
    endfunction

    function automatic signed [ACC_W-1:0] get_bias(input integer idx);
        get_bias = bias[idx*ACC_W +: ACC_W];
    endfunction

    integer o;
    integer i;
    logic signed [ACC_W-1:0] acc;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            done <= 1'b0;
            busy <= 1'b0;
            outputs <= '0;
        end else begin
            done <= 1'b0;
            if (start && !busy) begin
                busy <= 1'b1;
                for (o = 0; o < OUT_DIM; o = o + 1) begin
                    acc = get_bias(o);
                    for (i = 0; i < IN_DIM; i = i + 1) begin
                        acc = acc + get_activation(i) * get_weight(o, i);
                    end
                    outputs[o*ACC_W +: ACC_W] <= acc;
                end
                done <= 1'b1;
                busy <= 1'b0;
            end
        end
    end
endmodule
'''


_TB = r'''`timescale 1ns/1ps

module tiny_npu_tile_tb;
    localparam integer DATA_W = 8;
    localparam integer ACC_W = 32;
    localparam integer IN_DIM = 16;
    localparam integer OUT_DIM = 16;

    logic clk;
    logic rst_n;
    logic start;
    logic signed [DATA_W*IN_DIM-1:0] activations;
    logic signed [DATA_W*IN_DIM*OUT_DIM-1:0] weights;
    logic signed [ACC_W*OUT_DIM-1:0] bias;
    logic done;
    logic busy;
    logic signed [ACC_W*OUT_DIM-1:0] outputs;

    integer errors;

    tiny_npu_tile_16x16 dut (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .activations(activations),
        .weights(weights),
        .bias(bias),
        .done(done),
        .busy(busy),
        .outputs(outputs)
    );

    always #5 clk = ~clk;

    task automatic clear_all;
        begin
            activations = '0;
            weights = '0;
            bias = '0;
        end
    endtask

    task automatic set_activation(input integer idx, input integer value);
        begin
            activations[idx*DATA_W +: DATA_W] = value;
        end
    endtask

    task automatic set_weight(input integer out_idx, input integer in_idx, input integer value);
        begin
            weights[(out_idx*IN_DIM + in_idx)*DATA_W +: DATA_W] = value;
        end
    endtask

    task automatic set_bias(input integer idx, input integer value);
        begin
            bias[idx*ACC_W +: ACC_W] = value;
        end
    endtask

    function automatic signed [ACC_W-1:0] get_output(input integer idx);
        get_output = outputs[idx*ACC_W +: ACC_W];
    endfunction

    task automatic run_tile;
        begin
            @(negedge clk);
            start = 1'b1;
            @(negedge clk);
            start = 1'b0;
            #1;
            if (done !== 1'b1) begin
                $display("FAIL: done was not asserted");
                errors = errors + 1;
            end
        end
    endtask

    task automatic expect_output(input integer idx, input integer expected, input [127:0] label);
        begin
            if (get_output(idx) !== expected) begin
                $display("FAIL: %0s output[%0d] expected %0d got %0d", label, idx, expected, get_output(idx));
                errors = errors + 1;
            end
        end
    endtask

    function automatic integer digit_pixel(input integer digit, input integer idx);
        begin
            digit_pixel = 0;
            case (digit)
                0: digit_pixel = (idx==0 || idx==1 || idx==2 || idx==3 ||
                                  idx==4 || idx==7 || idx==8 || idx==11 ||
                                  idx==12 || idx==13 || idx==14 || idx==15);
                1: digit_pixel = (idx==1 || idx==5 || idx==9 || idx==13);
                2: digit_pixel = (idx==0 || idx==1 || idx==2 || idx==3 ||
                                  idx==7 || idx==8 || idx==9 || idx==10 ||
                                  idx==12 || idx==13 || idx==14 || idx==15);
                3: digit_pixel = (idx==0 || idx==1 || idx==2 || idx==3 ||
                                  idx==7 || idx==9 || idx==10 || idx==11 ||
                                  idx==12 || idx==13 || idx==14 || idx==15);
                4: digit_pixel = (idx==0 || idx==3 || idx==4 || idx==7 ||
                                  idx==8 || idx==9 || idx==10 || idx==11 || idx==15);
                5: digit_pixel = (idx==0 || idx==1 || idx==2 || idx==3 ||
                                  idx==4 || idx==8 || idx==9 || idx==10 ||
                                  idx==11 || idx==15 || idx==13 || idx==14);
                6: digit_pixel = (idx==0 || idx==1 || idx==2 || idx==3 ||
                                  idx==4 || idx==8 || idx==9 || idx==10 ||
                                  idx==11 || idx==12 || idx==13 || idx==14 || idx==15);
                7: digit_pixel = (idx==0 || idx==1 || idx==2 || idx==3 ||
                                  idx==7 || idx==11 || idx==15);
                8: digit_pixel = (idx==0 || idx==1 || idx==2 || idx==3 ||
                                  idx==4 || idx==7 || idx==8 || idx==9 ||
                                  idx==10 || idx==11 || idx==12 || idx==13 || idx==14 || idx==15);
                9: digit_pixel = (idx==0 || idx==1 || idx==2 || idx==3 ||
                                  idx==4 || idx==7 || idx==8 || idx==9 ||
                                  idx==10 || idx==11 || idx==15);
                default: digit_pixel = 0;
            endcase
        end
    endfunction

    task automatic load_digit_classifier;
        integer d;
        integer i;
        begin
            weights = '0;
            bias = '0;
            for (d = 0; d < 10; d = d + 1) begin
                for (i = 0; i < IN_DIM; i = i + 1) begin
                    set_weight(d, i, digit_pixel(d, i) ? 1 : -1);
                end
            end
        end
    endtask

    task automatic set_digit_input(input integer digit);
        integer i;
        begin
            activations = '0;
            for (i = 0; i < IN_DIM; i = i + 1) begin
                set_activation(i, digit_pixel(digit, i) ? 1 : -1);
            end
        end
    endtask

    task automatic expect_digit(input integer digit);
        integer d;
        integer best_digit;
        integer best_score;
        integer score;
        begin
            best_digit = 0;
            best_score = -1000000;
            for (d = 0; d < 10; d = d + 1) begin
                score = get_output(d);
                if (score > best_score) begin
                    best_score = score;
                    best_digit = d;
                end
            end
            if (best_digit != digit) begin
                $display("FAIL: digit expected %0d got %0d score %0d", digit, best_digit, best_score);
                errors = errors + 1;
            end else begin
                $display("PASS: digit %0d classified with score %0d", digit, best_score);
            end
        end
    endtask

    task automatic test_zero;
        integer o;
        begin
            clear_all();
            run_tile();
            for (o = 0; o < OUT_DIM; o = o + 1) begin
                expect_output(o, 0, "zero");
            end
        end
    endtask

    task automatic test_identity;
        integer i;
        begin
            clear_all();
            for (i = 0; i < IN_DIM; i = i + 1) begin
                set_activation(i, i - 8);
                set_weight(i, i, 1);
            end
            run_tile();
            for (i = 0; i < OUT_DIM; i = i + 1) begin
                expect_output(i, i - 8, "identity");
            end
        end
    endtask

    task automatic test_all_ones;
        integer o;
        integer i;
        begin
            clear_all();
            for (i = 0; i < IN_DIM; i = i + 1) begin
                set_activation(i, 1);
            end
            for (o = 0; o < OUT_DIM; o = o + 1) begin
                for (i = 0; i < IN_DIM; i = i + 1) begin
                    set_weight(o, i, 1);
                end
                set_bias(o, o);
            end
            run_tile();
            for (o = 0; o < OUT_DIM; o = o + 1) begin
                expect_output(o, 16 + o, "all_ones");
            end
        end
    endtask

    task automatic test_signed_checkerboard;
        integer i;
        integer expected;
        begin
            clear_all();
            expected = 0;
            for (i = 0; i < IN_DIM; i = i + 1) begin
                set_activation(i, (i % 2) ? -2 : 3);
                set_weight(0, i, (i % 2) ? -4 : 5);
                expected = expected + ((i % 2) ? 8 : 15);
            end
            set_bias(0, -7);
            expected = expected - 7;
            run_tile();
            expect_output(0, expected, "signed_checkerboard");
        end
    endtask

    task automatic test_digit_classifier;
        begin
            load_digit_classifier();
            set_digit_input(0);
            run_tile();
            expect_digit(0);
            set_digit_input(1);
            run_tile();
            expect_digit(1);
            set_digit_input(2);
            run_tile();
            expect_digit(2);
            set_digit_input(6);
            run_tile();
            expect_digit(6);
            set_digit_input(7);
            run_tile();
            expect_digit(7);
        end
    endtask

    initial begin
        clk = 1'b0;
        rst_n = 1'b0;
        start = 1'b0;
        errors = 0;
        clear_all();
        $dumpfile("wave/tiny_npu_tile.vcd");
        $dumpvars(0, tiny_npu_tile_tb);

        repeat (3) @(posedge clk);
        rst_n = 1'b1;

        test_zero();
        test_identity();
        test_all_ones();
        test_signed_checkerboard();
        test_digit_classifier();

        if (errors == 0) begin
            $display("ALL TESTS PASSED");
            $finish;
        end else begin
            $display("TESTS FAILED: %0d", errors);
            $fatal(1);
        end
    end
endmodule
'''


_YOSYS_SCRIPT = r'''read_verilog -sv rtl/tiny_npu_tile_16x16.sv
hierarchy -top tiny_npu_tile_16x16
proc
opt
fsm
opt
memory
opt
techmap
opt
stat
write_json synth/tiny_npu_tile_16x16.json
write_verilog synth/tiny_npu_tile_16x16_netlist.v
'''


_README = r'''# Tiny NPU Tile 16x16

This project is generated by CktClaw's deterministic Tiny NPU flow.

## Interface

- `activations`: 16 signed int8 inputs.
- `weights`: 16 x 16 signed int8 weights, flattened by output row then input column.
- `bias`: 16 signed int32 bias values.
- `outputs`: 16 signed int32 dot-product results.

## Local Run

```bash
iverilog -g2012 -Wall -o build/tiny_npu_tile_tb.vvp rtl/tiny_npu_tile_16x16.sv tb/tiny_npu_tile_tb.sv
vvp build/tiny_npu_tile_tb.vvp
yosys -s scripts/synth_yosys.ys
```

The testbench includes a 4x4 handwritten-digit prototype classifier demo that
uses the 16x16 tile as an inference engine.
'''
