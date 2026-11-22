`timescale 1ns/1ps

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
                                  idx==11 || idx==15 || idx==12 || idx==13 || idx==14);
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
