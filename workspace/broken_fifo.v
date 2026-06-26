// E2E fixture: FIFO with functional bug (Prompt 8 — verification should FAIL)
module broken_fifo #(
    parameter DEPTH = 4,
    parameter WIDTH = 8
) (
    input  wire             clk,
    input  wire             rst,
    input  wire             wr_en,
    input  wire             rd_en,
    input  wire [WIDTH-1:0] din,
    output reg  [WIDTH-1:0] dout,
    output wire             full,
    output wire             empty
);
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [2:0] wr_ptr, rd_ptr;
    reg [2:0] count;

    assign full  = (count == DEPTH);
    assign empty = (count == 0);

    always @(posedge clk) begin
        if (rst) begin
            wr_ptr <= 0;
            rd_ptr <= 0;
            count  <= 0;
            dout   <= 0;
        end else begin
            if (wr_en && !full) begin
                mem[wr_ptr[1:0]] <= din;
                wr_ptr <= wr_ptr + 1;
                count  <= count + 1;
            end
            // Bug: read does not decrement count and returns wrong slot
            if (rd_en && !empty) begin
                dout <= mem[rd_ptr[1:0] + 1];  // off-by-one read
                rd_ptr <= rd_ptr + 1;
                // missing: count <= count - 1;
            end
        end
    end
endmodule
