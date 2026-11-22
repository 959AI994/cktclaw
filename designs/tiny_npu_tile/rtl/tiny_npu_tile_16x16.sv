// 16x16 Tiny NPU Tile
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
