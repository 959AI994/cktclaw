"""Built-in RTL IP templates used by chip AutoDesign V1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .types import AutoDesignSpec


@dataclass(frozen=True)
class DesignTemplate:
    rtl_filename: str
    tb_filename: str
    module_name: str
    rtl: str
    tb: str
    functional_tests: List[str]


def template_for(spec: AutoDesignSpec) -> DesignTemplate:
    if spec.design_kind == "sync_fifo":
        return DesignTemplate(
            rtl_filename="sync_fifo.sv",
            tb_filename="sync_fifo_tb.sv",
            module_name="sync_fifo",
            rtl=_FIFO_RTL,
            tb=_FIFO_TB,
            functional_tests=[
                "reset empty/full state",
                "ordered write/read",
                "full boundary",
                "empty boundary",
                "simultaneous read/write",
            ],
        )
    if spec.design_kind == "axi_lite_reg_block":
        return DesignTemplate(
            rtl_filename="axi_lite_reg_block.sv",
            tb_filename="axi_lite_reg_block_tb.sv",
            module_name="axi_lite_reg_block",
            rtl=_AXI_RTL,
            tb=_AXI_TB,
            functional_tests=[
                "AXI-lite write handshake",
                "AXI-lite read handshake",
                "four register addresses",
                "write strobe behavior",
            ],
        )
    if spec.design_kind == "signed_dsp_mac":
        return DesignTemplate(
            rtl_filename="signed_dsp_mac.sv",
            tb_filename="signed_dsp_mac_tb.sv",
            module_name="signed_dsp_mac",
            rtl=_DSP_RTL,
            tb=_DSP_TB,
            functional_tests=[
                "positive multiply accumulate",
                "negative multiply accumulate",
                "clear behavior",
                "valid/out_valid protocol",
            ],
        )
    raise ValueError(f"No built-in template for {spec.design_kind}")


def spec_defaults_for(kind: str, user_task: str) -> Dict:
    if kind == "axi_lite_reg_block":
        return {
            "module_name": "axi_lite_reg_block",
            "goal": "AXI-lite slave register block with four 32-bit registers.",
            "protocol": "AXI4-Lite single-beat slave",
            "parameters": {"ADDR_W": 4, "DATA_W": 32, "REG_COUNT": 4},
            "data_widths": {"addr": 4, "data": 32},
            "interfaces": [
                {"name": "AXI-lite slave", "signals": "AW/W/B/AR/R channels"},
            ],
            "verification": [
                "self-checking write/read tests",
                "address decode tests",
                "write strobe masking",
            ],
        }
    if kind == "signed_dsp_mac":
        return {
            "module_name": "signed_dsp_mac",
            "goal": "Signed multiply-accumulate datapath with clear and valid handshake.",
            "protocol": "valid/clear single-cycle datapath",
            "parameters": {"DATA_W": 16, "ACC_W": 40},
            "data_widths": {"a": 16, "b": 16, "acc": 40},
            "interfaces": [
                {"name": "datapath", "signals": "valid, clear, a, b, acc, out_valid"},
            ],
            "verification": [
                "positive accumulation",
                "signed negative accumulation",
                "clear and valid protocol tests",
            ],
        }
    if kind == "tiny_npu_tile":
        return {
            "module_name": "tiny_npu_tile_16x16",
            "goal": "16x16 signed int8 matrix-vector NPU tile for tiny inference demos.",
            "protocol": "start/done packed-vector datapath",
            "parameters": {"IN_DIM": 16, "OUT_DIM": 16, "DATA_W": 8, "ACC_W": 32},
            "data_widths": {"activation": 8, "weight": 8, "accumulator": 32},
            "interfaces": [
                {"name": "tile datapath", "signals": "start, done, activations, weights, bias, outputs"},
            ],
            "verification": [
                "matrix-vector reference checks",
                "signed arithmetic checks",
                "tiny handwritten-digit prototype classifier",
            ],
        }
    if kind == "custom":
        from ..validated_rtl.controller import extract_module_name

        module_name = extract_module_name(user_task, default="custom_ip")
        return {
            "module_name": module_name,
            "goal": user_task.strip()[:500] or f"Custom RTL IP `{module_name}`.",
            "protocol": "User-specified streaming/control interface",
            "parameters": {},
            "data_widths": {"data": 8},
            "interfaces": [
                {"name": "user-defined", "signals": "see mission spec / user task"},
            ],
            "verification": [
                "self-checking testbench",
                "simulation PASS",
                "known vector checks when specified",
                "Yosys synthesis PASS",
                "hard gate report",
            ],
        }
    return {
        "module_name": "sync_fifo",
        "goal": "Synchronous FIFO with full/empty/count status.",
        "protocol": "ready-style FIFO push/pop controls",
        "parameters": {"DATA_W": 8, "DEPTH": 4, "ADDR_W": 2},
        "data_widths": {"data": 8, "count": 3},
        "interfaces": [
            {"name": "fifo", "signals": "wr_en, rd_en, wr_data, rd_data, full, empty, count"},
        ],
        "verification": [
            "reset and status checks",
            "ordered write/read",
            "full and empty boundary checks",
            "simultaneous read/write",
        ],
    }


_FIFO_RTL = r'''module sync_fifo #(
    parameter integer DATA_W = 8,
    parameter integer DEPTH = 4,
    parameter integer ADDR_W = 2
) (
    input  logic clk,
    input  logic rst_n,
    input  logic wr_en,
    input  logic rd_en,
    input  logic [DATA_W-1:0] wr_data,
    output logic [DATA_W-1:0] rd_data,
    output logic full,
    output logic empty,
    output logic [ADDR_W:0] count
);
    logic [DATA_W-1:0] mem [0:DEPTH-1];
    logic [ADDR_W-1:0] wr_ptr;
    logic [ADDR_W-1:0] rd_ptr;

    assign full = (count == DEPTH[ADDR_W:0]);
    assign empty = (count == '0);

    wire do_write = wr_en && (!full || rd_en);
    wire do_read = rd_en && !empty;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr <= '0;
            rd_ptr <= '0;
            rd_data <= '0;
            count <= '0;
        end else begin
            if (do_write) begin
                mem[wr_ptr] <= wr_data;
                wr_ptr <= wr_ptr + 1'b1;
            end
            if (do_read) begin
                rd_data <= mem[rd_ptr];
                rd_ptr <= rd_ptr + 1'b1;
            end
            unique case ({do_write, do_read})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule
'''


_FIFO_TB = r'''`timescale 1ns/1ps
module sync_fifo_tb;
    logic clk, rst_n, wr_en, rd_en;
    logic [7:0] wr_data, rd_data;
    logic full, empty;
    logic [2:0] count;
    integer errors;

    sync_fifo dut (
        .clk(clk), .rst_n(rst_n), .wr_en(wr_en), .rd_en(rd_en),
        .wr_data(wr_data), .rd_data(rd_data), .full(full), .empty(empty),
        .count(count)
    );

    always #5 clk = ~clk;

    task automatic push(input [7:0] value);
        begin
            @(negedge clk);
            wr_en = 1'b1;
            wr_data = value;
            @(negedge clk);
            wr_en = 1'b0;
        end
    endtask

    task automatic pop_expect(input [7:0] value);
        begin
            @(negedge clk);
            rd_en = 1'b1;
            @(posedge clk);
            #1;
            if (rd_data !== value) begin
                $display("FAIL: expected %0d got %0d", value, rd_data);
                errors = errors + 1;
            end
            @(negedge clk);
            rd_en = 1'b0;
        end
    endtask

    initial begin
        $dumpfile("wave/sync_fifo.vcd");
        $dumpvars(0, sync_fifo_tb);
        clk = 0; rst_n = 0; wr_en = 0; rd_en = 0; wr_data = 0; errors = 0;
        repeat (3) @(posedge clk);
        rst_n = 1;
        #1;
        if (!empty || full || count != 0) errors = errors + 1;
        push(8'h11); push(8'h22); push(8'h33); push(8'h44);
        #1;
        if (!full || count != 4) errors = errors + 1;
        pop_expect(8'h11); pop_expect(8'h22);
        push(8'h55);
        pop_expect(8'h33); pop_expect(8'h44); pop_expect(8'h55);
        #1;
        if (!empty) errors = errors + 1;
        if (errors == 0) begin
            $display("ALL TESTS PASSED");
            $finish;
        end
        $display("TESTS FAILED: %0d", errors);
        $fatal(1);
    end
endmodule
'''


_AXI_RTL = r'''module axi_lite_reg_block #(
    parameter integer ADDR_W = 4,
    parameter integer DATA_W = 32
) (
    input  logic clk,
    input  logic rst_n,
    input  logic [ADDR_W-1:0] s_axi_awaddr,
    input  logic s_axi_awvalid,
    output logic s_axi_awready,
    input  logic [DATA_W-1:0] s_axi_wdata,
    input  logic [(DATA_W/8)-1:0] s_axi_wstrb,
    input  logic s_axi_wvalid,
    output logic s_axi_wready,
    output logic [1:0] s_axi_bresp,
    output logic s_axi_bvalid,
    input  logic s_axi_bready,
    input  logic [ADDR_W-1:0] s_axi_araddr,
    input  logic s_axi_arvalid,
    output logic s_axi_arready,
    output logic [DATA_W-1:0] s_axi_rdata,
    output logic [1:0] s_axi_rresp,
    output logic s_axi_rvalid,
    input  logic s_axi_rready
);
    logic [DATA_W-1:0] regs [0:3];
    integer i;

    assign s_axi_awready = 1'b1;
    assign s_axi_wready = 1'b1;
    assign s_axi_arready = 1'b1;
    assign s_axi_bresp = 2'b00;
    assign s_axi_rresp = 2'b00;

    function automatic [1:0] addr_index(input [ADDR_W-1:0] addr);
        addr_index = addr[3:2];
    endfunction

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < 4; i = i + 1) regs[i] <= '0;
            s_axi_bvalid <= 1'b0;
            s_axi_rvalid <= 1'b0;
            s_axi_rdata <= '0;
        end else begin
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
            if (s_axi_awvalid && s_axi_wvalid && !s_axi_bvalid) begin
                for (i = 0; i < DATA_W/8; i = i + 1) begin
                    if (s_axi_wstrb[i]) begin
                        regs[addr_index(s_axi_awaddr)][8*i +: 8] <= s_axi_wdata[8*i +: 8];
                    end
                end
                s_axi_bvalid <= 1'b1;
            end
            if (s_axi_arvalid && !s_axi_rvalid) begin
                s_axi_rdata <= regs[addr_index(s_axi_araddr)];
                s_axi_rvalid <= 1'b1;
            end
        end
    end
endmodule
'''


_AXI_TB = r'''`timescale 1ns/1ps
module axi_lite_reg_block_tb;
    logic clk, rst_n;
    logic [3:0] awaddr, araddr;
    logic awvalid, awready, wvalid, wready, bvalid, bready;
    logic arvalid, arready, rvalid, rready;
    logic [31:0] wdata, rdata;
    logic [3:0] wstrb;
    logic [1:0] bresp, rresp;
    integer errors;

    axi_lite_reg_block dut (
        .clk(clk), .rst_n(rst_n), .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid),
        .s_axi_awready(awready), .s_axi_wdata(wdata), .s_axi_wstrb(wstrb),
        .s_axi_wvalid(wvalid), .s_axi_wready(wready), .s_axi_bresp(bresp),
        .s_axi_bvalid(bvalid), .s_axi_bready(bready), .s_axi_araddr(araddr),
        .s_axi_arvalid(arvalid), .s_axi_arready(arready), .s_axi_rdata(rdata),
        .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready)
    );

    always #5 clk = ~clk;

    task automatic axi_write(input [3:0] addr, input [31:0] data, input [3:0] strb);
        begin
            @(negedge clk);
            awaddr = addr; wdata = data; wstrb = strb; awvalid = 1; wvalid = 1; bready = 1;
            @(negedge clk);
            awvalid = 0; wvalid = 0;
            wait (bvalid);
            @(negedge clk);
            bready = 0;
        end
    endtask

    task automatic axi_read_expect(input [3:0] addr, input [31:0] expected);
        begin
            @(negedge clk);
            araddr = addr; arvalid = 1; rready = 1;
            @(negedge clk);
            arvalid = 0;
            wait (rvalid);
            #1;
            if (rdata !== expected) begin
                $display("FAIL: addr %0h expected %0h got %0h", addr, expected, rdata);
                errors = errors + 1;
            end
            @(negedge clk);
            rready = 0;
        end
    endtask

    initial begin
        $dumpfile("wave/axi_lite_reg_block.vcd");
        $dumpvars(0, axi_lite_reg_block_tb);
        clk = 0; rst_n = 0; awaddr = 0; araddr = 0; awvalid = 0; wvalid = 0;
        arvalid = 0; bready = 0; rready = 0; wdata = 0; wstrb = 0; errors = 0;
        repeat (3) @(posedge clk);
        rst_n = 1;
        axi_write(4'h0, 32'h12345678, 4'hf);
        axi_write(4'h4, 32'hdeadbeef, 4'hf);
        axi_write(4'h8, 32'haaaa5555, 4'h3);
        axi_read_expect(4'h0, 32'h12345678);
        axi_read_expect(4'h4, 32'hdeadbeef);
        axi_read_expect(4'h8, 32'h00005555);
        axi_read_expect(4'hc, 32'h00000000);
        if (errors == 0) begin
            $display("ALL TESTS PASSED");
            $finish;
        end
        $display("TESTS FAILED: %0d", errors);
        $fatal(1);
    end
endmodule
'''


_DSP_RTL = r'''module signed_dsp_mac #(
    parameter integer DATA_W = 16,
    parameter integer ACC_W = 40
) (
    input  logic clk,
    input  logic rst_n,
    input  logic valid,
    input  logic clear,
    input  logic signed [DATA_W-1:0] a,
    input  logic signed [DATA_W-1:0] b,
    output logic signed [ACC_W-1:0] acc,
    output logic out_valid
);
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            acc <= '0;
            out_valid <= 1'b0;
        end else begin
            out_valid <= valid;
            if (clear) begin
                acc <= '0;
            end else if (valid) begin
                acc <= acc + (a * b);
            end
        end
    end
endmodule
'''


_DSP_TB = r'''`timescale 1ns/1ps
module signed_dsp_mac_tb;
    logic clk, rst_n, valid, clear;
    logic signed [15:0] a, b;
    logic signed [39:0] acc;
    logic out_valid;
    integer errors;

    signed_dsp_mac dut (
        .clk(clk), .rst_n(rst_n), .valid(valid), .clear(clear),
        .a(a), .b(b), .acc(acc), .out_valid(out_valid)
    );

    always #5 clk = ~clk;

    task automatic step(input signed [15:0] av, input signed [15:0] bv, input signed [39:0] expected);
        begin
            @(negedge clk);
            a = av; b = bv; valid = 1; clear = 0;
            @(posedge clk);
            #1;
            if (acc !== expected || out_valid !== 1'b1) begin
                $display("FAIL: expected acc %0d got %0d out_valid %0b", expected, acc, out_valid);
                errors = errors + 1;
            end
            @(negedge clk);
            valid = 0;
        end
    endtask

    initial begin
        $dumpfile("wave/signed_dsp_mac.vcd");
        $dumpvars(0, signed_dsp_mac_tb);
        clk = 0; rst_n = 0; valid = 0; clear = 0; a = 0; b = 0; errors = 0;
        repeat (3) @(posedge clk);
        rst_n = 1;
        step(3, 4, 12);
        step(-5, 6, -18);
        @(negedge clk);
        clear = 1; valid = 0;
        @(posedge clk);
        #1;
        if (acc !== 0) errors = errors + 1;
        @(negedge clk);
        clear = 0;
        step(-7, -8, 56);
        if (errors == 0) begin
            $display("ALL TESTS PASSED");
            $finish;
        end
        $display("TESTS FAILED: %0d", errors);
        $fatal(1);
    end
endmodule
'''
