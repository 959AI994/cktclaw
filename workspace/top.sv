`include "defs.svh"

module top (
    input  wire       clk,
    input  wire       rst,
    input  wire [7:0] a,
    input  wire [7:0] b,
    output reg  [7:0] sum
);
    // Intentional style issues for verible lint smoke (Prompt 10)
    always @(posedge clk) begin
        if(rst)begin
            sum <= 0;
        end else begin
            sum <= a + b;  // no overflow handling — ok for smoke
        end
    end
endmodule
