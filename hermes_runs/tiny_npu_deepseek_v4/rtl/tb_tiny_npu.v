//============================================================================
// tb_tiny_npu.v - Handwritten digit "6" smoke test for tiny_npu
//============================================================================

`timescale 1ns / 1ps

module tb_tiny_npu;

    reg         clk;
    reg         rst_n;
    reg  [7:0]  addr;
    reg  [31:0] wr_data;
    reg         wr_en;
    reg         rd_en;
    wire [31:0] rd_data;
    wire        done_out;
    wire        busy_out;

    localparam signed [7:0] W_ON  =  8'sd1;
    localparam signed [7:0] W_OFF = -8'sd1;

    tiny_npu dut (
        .clk(clk),
        .rst_n(rst_n),
        .addr(addr),
        .wr_data(wr_data),
        .wr_en(wr_en),
        .rd_en(rd_en),
        .rd_data(rd_data),
        .done_out(done_out),
        .busy_out(busy_out)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    function [31:0] pack4;
        input signed [7:0] p0;
        input signed [7:0] p1;
        input signed [7:0] p2;
        input signed [7:0] p3;
        begin
            pack4 = {p3[7:0], p2[7:0], p1[7:0], p0[7:0]};
        end
    endfunction

    task reg_write;
        input [7:0] a;
        input [31:0] d;
        begin
            @(posedge clk);
            addr    <= a;
            wr_data <= d;
            wr_en   <= 1'b1;
            rd_en   <= 1'b0;
            @(posedge clk);
            wr_en   <= 1'b0;
            wr_data <= 32'd0;
        end
    endtask

    task reg_read;
        input  [7:0] a;
        output [31:0] d;
        begin
            @(posedge clk);
            addr  <= a;
            wr_en <= 1'b0;
            rd_en <= 1'b1;
            @(posedge clk);
            #1;
            d     = rd_data;
            rd_en <= 1'b0;
        end
    endtask

    task write_weight_row;
        input [5:0]  row;
        input [31:0] w0;
        input [31:0] w1;
        input [31:0] w2;
        input [31:0] w3;
        begin
            reg_write(8'h10 + row * 8'd4 + 8'd0, w0);
            reg_write(8'h10 + row * 8'd4 + 8'd1, w1);
            reg_write(8'h10 + row * 8'd4 + 8'd2, w2);
            reg_write(8'h10 + row * 8'd4 + 8'd3, w3);
        end
    endtask

    task write_template;
        input [5:0] row;
        input signed [7:0] p00;
        input signed [7:0] p01;
        input signed [7:0] p02;
        input signed [7:0] p03;
        input signed [7:0] p10;
        input signed [7:0] p11;
        input signed [7:0] p12;
        input signed [7:0] p13;
        input signed [7:0] p20;
        input signed [7:0] p21;
        input signed [7:0] p22;
        input signed [7:0] p23;
        input signed [7:0] p30;
        input signed [7:0] p31;
        input signed [7:0] p32;
        input signed [7:0] p33;
        begin
            write_weight_row(row,
                pack4(p00, p01, p02, p03),
                pack4(p10, p11, p12, p13),
                pack4(p20, p21, p22, p23),
                pack4(p30, p31, p32, p33));
        end
    endtask

    task load_digit_templates;
        begin
            write_template(0, W_OFF,W_ON, W_ON, W_OFF,
                              W_ON, W_OFF,W_OFF,W_ON,
                              W_ON, W_OFF,W_OFF,W_ON,
                              W_OFF,W_ON, W_ON, W_OFF);
            write_template(1, W_OFF,W_OFF,W_ON, W_OFF,
                              W_OFF,W_ON, W_ON, W_OFF,
                              W_OFF,W_OFF,W_ON, W_OFF,
                              W_OFF,W_ON, W_ON, W_ON);
            write_template(2, W_ON, W_ON, W_ON, W_OFF,
                              W_OFF,W_OFF,W_OFF,W_ON,
                              W_OFF,W_ON, W_ON, W_OFF,
                              W_ON, W_ON, W_ON, W_ON);
            write_template(3, W_ON, W_ON, W_ON, W_OFF,
                              W_OFF,W_OFF,W_OFF,W_ON,
                              W_OFF,W_ON, W_ON, W_OFF,
                              W_ON, W_ON, W_ON, W_OFF);
            write_template(4, W_ON, W_OFF,W_OFF,W_ON,
                              W_ON, W_OFF,W_OFF,W_ON,
                              W_ON, W_ON, W_ON, W_ON,
                              W_OFF,W_OFF,W_OFF,W_ON);
            write_template(5, W_ON, W_ON, W_ON, W_ON,
                              W_ON, W_OFF,W_OFF,W_OFF,
                              W_ON, W_ON, W_ON, W_OFF,
                              W_OFF,W_OFF,W_OFF,W_ON);
            write_template(6, W_OFF,W_ON, W_ON, W_OFF,
                              W_ON, W_OFF,W_OFF,W_OFF,
                              W_ON, W_ON, W_ON, W_OFF,
                              W_ON, W_OFF,W_OFF,W_ON);
            write_template(7, W_ON, W_ON, W_ON, W_ON,
                              W_OFF,W_OFF,W_OFF,W_ON,
                              W_OFF,W_OFF,W_ON, W_OFF,
                              W_OFF,W_ON, W_OFF,W_OFF);
            write_template(8, W_OFF,W_ON, W_ON, W_OFF,
                              W_ON, W_OFF,W_OFF,W_ON,
                              W_OFF,W_ON, W_ON, W_OFF,
                              W_ON, W_OFF,W_OFF,W_ON);
            write_template(9, W_OFF,W_ON, W_ON, W_OFF,
                              W_ON, W_OFF,W_OFF,W_ON,
                              W_OFF,W_ON, W_ON, W_ON,
                              W_OFF,W_OFF,W_OFF,W_ON);

            write_template(10, W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF);
            write_template(11, W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF);
            write_template(12, W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF);
            write_template(13, W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF);
            write_template(14, W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF);
            write_template(15, W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF,
                               W_OFF,W_OFF,W_OFF,W_OFF);
        end
    endtask

    integer i;
    reg signed [31:0] scores [0:9];
    reg signed [31:0] max_score;
    integer max_digit;

    initial begin
        $dumpfile("tiny_npu.vcd");
        $dumpvars(0, tb_tiny_npu);

        rst_n   = 1'b0;
        addr    = 8'd0;
        wr_data = 32'd0;
        wr_en   = 1'b0;
        rd_en   = 1'b0;
        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        repeat (2) @(posedge clk);

        $display("============================================================");
        $display(" Tiny NPU handwritten digit 6 recognition");
        $display(" 4x4 input pattern:");
        $display("   0  80  80   0");
        $display("  80   0   0   0");
        $display("  80  80  80   0");
        $display("  80   0   0  80");
        $display("============================================================");

        reg_write(8'h00, pack4(8'sd0,  8'sd80, 8'sd80, 8'sd0));
        reg_write(8'h04, pack4(8'sd80, 8'sd0,  8'sd0,  8'sd0));
        reg_write(8'h08, pack4(8'sd80, 8'sd80, 8'sd80, 8'sd0));
        reg_write(8'h0c, pack4(8'sd80, 8'sd0,  8'sd0,  8'sd80));

        load_digit_templates();

        $display("[RUN] Starting 16x16 int8 MAC tile");
        reg_write(8'hf0, 32'h00000001);
        wait (done_out === 1'b1);
        @(posedge clk);

        max_digit = 0;
        max_score = -32'sd2147483647;
        $display("[READOUT] digit scores");
        for (i = 0; i < 10; i = i + 1) begin
            reg_read(8'h50 + i[7:0], scores[i]);
            $display("  digit[%0d] = %0d", i, scores[i]);
            if (scores[i] > max_score) begin
                max_score = scores[i];
                max_digit = i;
            end
        end

        $display("============================================================");
        $display(" RESULT: predicted digit %0d, score %0d", max_digit, max_score);
        if (max_digit == 6) begin
            $display(" TEST PASS");
            $display("============================================================");
            $finish;
        end

        $display(" TEST FAIL: expected digit 6");
        $display("============================================================");
        $fatal(1);
    end

endmodule
