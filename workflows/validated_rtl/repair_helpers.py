"""Deterministic RTL/TB repair helpers for validated RTL and chip-mission flows."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def is_compile_log(output: str) -> bool:
    lowered = output.lower()
    if "compile failed" in lowered:
        return True
    for line in output.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("error:") or stripped.startswith("sorry:"):
            return True
    return False


def is_compile_failure(sim: Dict[str, Any]) -> bool:
    if sim.get("status") != "FAIL":
        return False
    issues = sim.get("issues") or []
    if any("compile failed" in str(item).lower() for item in issues):
        return True
    return is_compile_log(str(sim.get("output") or ""))


def crc8_known_vector_tb_source(module_name: str) -> str:
    tb_module = f"{module_name}_tb"
    return "\n".join([
        "// Minimal iverilog-compatible CRC-8/ATM known-vector testbench",
        "`timescale 1ns/1ps",
        "",
        f"module {tb_module};",
        "  reg clk;",
        "  reg rst_n;",
        "  reg data_valid;",
        "  reg [7:0] data_in;",
        "  reg data_last;",
        "  wire crc_valid;",
        "  wire [7:0] crc_out;",
        "",
        f"  {module_name} dut (",
        "    .clk(clk),",
        "    .rst_n(rst_n),",
        "    .data_valid(data_valid),",
        "    .data_in(data_in),",
        "    .data_last(data_last),",
        "    .crc_valid(crc_valid),",
        "    .crc_out(crc_out)",
        "  );",
        "",
        "  initial clk = 0;",
        "  always #5 clk = ~clk;",
        "",
        "  function [7:0] test_byte;",
        "    input [3:0] idx;",
        "    begin",
        "      case (idx)",
        "        4'd0: test_byte = 8'd49;",
        "        4'd1: test_byte = 8'd50;",
        "        4'd2: test_byte = 8'd51;",
        "        4'd3: test_byte = 8'd52;",
        "        4'd4: test_byte = 8'd53;",
        "        4'd5: test_byte = 8'd54;",
        "        4'd6: test_byte = 8'd55;",
        "        4'd7: test_byte = 8'd56;",
        "        default: test_byte = 8'd57;",
        "      endcase",
        "    end",
        "  endfunction",
        "",
        "  integer idx;",
        "  reg check_pass;",
        "  initial begin",
        "    rst_n = 0;",
        "    data_valid = 0;",
        "    data_in = 0;",
        "    data_last = 0;",
        "    check_pass = 0;",
        "    #20 rst_n = 1;",
        "    #10;",
        "    for (idx = 0; idx < 9; idx = idx + 1) begin",
        "      @(posedge clk);",
        "      data_in = test_byte(idx[3:0]);",
        "      data_valid = 1;",
        "      data_last = (idx == 8);",
        "      #10;",
        "    end",
        "    @(posedge clk);",
        "    #5;",
        "    if (crc_valid === 1'b1 && crc_out == 8'hF4) begin",
        "      $display(\"PASS: CRC = %h (expected f4)\", crc_out);",
        "      $display(\"TEST PASSED\");",
        "      check_pass = 1;",
        "    end else begin",
        "      $display(\"FAIL: crc_valid=%b crc_out=%h (expected valid=1 out=f4)\", crc_valid, crc_out);",
        "    end",
        "    if (!check_pass) $fatal(1);",
        "    #20 $finish;",
        "  end",
        "endmodule",
        "",
    ])


def apply_deterministic_iverilog_tb_repair(
    project_dir: Path,
    module_name: str,
) -> bool:
    """Replace TB with a minimal iverilog-compatible CRC-8 known-vector testbench."""
    if "crc8" not in module_name.lower():
        return False
    tb_dir = project_dir / "tb"
    tb_dir.mkdir(parents=True, exist_ok=True)
    tb_name = f"{module_name}_tb.v"
    tb_path = tb_dir / tb_name
    tb_path.write_text(crc8_known_vector_tb_source(module_name), encoding="utf-8")
    return True


def write_crc8_known_vector_tb(tb_dir: Path, module_name: str, tb_name: str) -> Path:
    path = tb_dir / tb_name
    path.write_text(crc8_known_vector_tb_source(module_name), encoding="utf-8")
    return path
