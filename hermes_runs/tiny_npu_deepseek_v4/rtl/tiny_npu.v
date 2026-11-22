//============================================================================
// tiny_npu.v - Tiny NPU with a 16x16 signed int8 MAC tile
//
// Address map:
//   0x00,0x04,0x08,0x0c  input vector, 4 signed int8 values per word
//   0x10..0x4f           16x16 weight matrix, row-major, 4 int8 per word
//   0x50..0x5f           16 signed int32 output scores
//   0xf0                 control: write bit 0 to start
//   0xf4                 status: {30'b0, done, busy}
//============================================================================

module tiny_npu (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  addr,
    input  wire [31:0] wr_data,
    input  wire        wr_en,
    input  wire        rd_en,
    output reg  [31:0] rd_data,
    output wire        done_out,
    output wire        busy_out
);

    localparam N       = 16;
    localparam S_IDLE  = 2'd0;
    localparam S_MAC   = 2'd1;
    localparam S_STORE = 2'd2;
    localparam S_DONE  = 2'd3;

    reg signed [7:0]  input_buf  [0:N-1];
    reg signed [7:0]  weight_buf [0:N-1][0:N-1];
    reg signed [31:0] acc        [0:N-1];
    reg signed [31:0] output_buf [0:N-1];

    reg [1:0] state;
    reg [4:0] col;
    reg       status_busy;
    reg       status_done;

    assign busy_out = status_busy;
    assign done_out = status_done;

    wire [3:0] input_base      = {addr[3:2], 2'b00};
    wire [7:0] weight_offset   = addr - 8'h10;
    wire [3:0] weight_row      = weight_offset[5:2];
    wire [3:0] weight_col_base = {weight_offset[1:0], 2'b00};

    integer i;
    integer j;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            col         <= 5'd0;
            rd_data     <= 32'd0;
            status_busy <= 1'b0;
            status_done <= 1'b0;
            for (i = 0; i < N; i = i + 1) begin
                input_buf[i]  <= 8'sd0;
                acc[i]        <= 32'sd0;
                output_buf[i] <= 32'sd0;
                for (j = 0; j < N; j = j + 1) begin
                    weight_buf[i][j] <= 8'sd0;
                end
            end
        end else begin
            if (wr_en) begin
                if (addr[7:4] == 4'h0) begin
                    input_buf[input_base + 4'd0] <= wr_data[7:0];
                    input_buf[input_base + 4'd1] <= wr_data[15:8];
                    input_buf[input_base + 4'd2] <= wr_data[23:16];
                    input_buf[input_base + 4'd3] <= wr_data[31:24];
                end else if (addr >= 8'h10 && addr <= 8'h4f) begin
                    weight_buf[weight_row][weight_col_base + 4'd0] <= wr_data[7:0];
                    weight_buf[weight_row][weight_col_base + 4'd1] <= wr_data[15:8];
                    weight_buf[weight_row][weight_col_base + 4'd2] <= wr_data[23:16];
                    weight_buf[weight_row][weight_col_base + 4'd3] <= wr_data[31:24];
                end
            end

            if (rd_en) begin
                if (addr[7:4] == 4'h0) begin
                    rd_data <= {
                        input_buf[input_base + 4'd3],
                        input_buf[input_base + 4'd2],
                        input_buf[input_base + 4'd1],
                        input_buf[input_base + 4'd0]
                    };
                end else if (addr[7:4] == 4'h5) begin
                    rd_data <= output_buf[addr[3:0]];
                end else if (addr == 8'hf4) begin
                    rd_data <= {30'd0, status_done, status_busy};
                end else begin
                    rd_data <= 32'd0;
                end
            end

            case (state)
                S_IDLE: begin
                    status_busy <= 1'b0;
                    if (wr_en && addr == 8'hf0 && wr_data[0]) begin
                        col         <= 5'd0;
                        status_busy <= 1'b1;
                        status_done <= 1'b0;
                        for (i = 0; i < N; i = i + 1) begin
                            acc[i] <= 32'sd0;
                        end
                        state <= S_MAC;
                    end
                end

                S_MAC: begin
                    for (i = 0; i < N; i = i + 1) begin
                        acc[i] <= acc[i]
                            + ($signed(weight_buf[i][col[3:0]])
                            *  $signed(input_buf[col[3:0]]));
                    end
                    if (col == 5'd15) begin
                        state <= S_STORE;
                    end else begin
                        col <= col + 5'd1;
                    end
                end

                S_STORE: begin
                    for (i = 0; i < N; i = i + 1) begin
                        output_buf[i] <= acc[i];
                    end
                    status_busy <= 1'b0;
                    status_done <= 1'b1;
                    state       <= S_DONE;
                end

                S_DONE: begin
                    state <= S_IDLE;
                end

                default: begin
                    state <= S_IDLE;
                end
            endcase
        end
    end

endmodule
