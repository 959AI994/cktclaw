// E2E fixture: intentional bugs for RTL repair (Prompt 2)
// Expected fix: sync reset clears count; else increment each clk
module bad_counter (
    input  wire       clk,
    input  wire       rst_n,
    output reg  [7:0] count
);
    // Bug 1: async reset style with active-high reset (spec wants sync, active-high rst)
    // Bug 2: width mismatch — assigns 9-bit expression to 8-bit reg
    always @(posedge clk or posedge rst_n) begin
        if (rst_n)
            count <= 9'd0;          // should be sync reset when rst high
        else
            count <= count + 9'd2;  // should be +1, width should match [7:0]
    end
endmodule
