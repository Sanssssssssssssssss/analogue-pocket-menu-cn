// SPDX-License-Identifier: MIT
// Two restoring-division bits per 32 MHz clock. The native CPU advances once
// per 16 clocks; its DIV microcode loads both operands before selecting DIV.
// No CPU clock, clock enable, microcode, or timing exception is changed.
module pm_divide (
    input wire clk,
    input wire [15:0] dividend,
    input wire [7:0] divisor,
    input wire size,
    output wire [15:0] result,
    output wire [3:0] flags
);
    function automatic [24:0] divide_two (
        input [8:0] remainder_in,
        input [15:0] quotient_in,
        input [7:0] denominator
    );
        reg [8:0] remainder_work;
        reg [15:0] quotient_work;
        integer bit_index;
        begin
            remainder_work = remainder_in;
            quotient_work = quotient_in;
            for (bit_index=0; bit_index<2; bit_index=bit_index+1) begin
                remainder_work = {remainder_work[7:0], quotient_work[15]};
                quotient_work = {quotient_work[14:0], 1'b0};
                if (remainder_work >= {1'b0, denominator}) begin
                    remainder_work = remainder_work - {1'b0, denominator};
                    quotient_work[0] = 1'b1;
                end
            end
            divide_two = {remainder_work, quotient_work};
        end
    endfunction

    wire [15:0] quotient [0:8];
    wire [8:0] remainder_full [0:8];
    wire [15:0] quotient_low [0:8];
    wire [8:0] remainder_low [0:8];
    wire [7:0] denominator [0:8];
    wire operand_size [0:8];
    assign quotient[0] = dividend;
    assign quotient_low[0] = {8'd0, dividend[7:0]};
    assign remainder_full[0] = 9'd0;
    assign remainder_low[0] = 9'd0;
    assign denominator[0] = divisor;
    assign operand_size[0] = size;
    genvar stage;
    generate for (stage=0; stage<8; stage=stage+1) begin: pipe
        reg [24:0] full_step;
        reg [24:0] low_step;
        reg [7:0] denominator_step;
        reg size_step;
        always @(posedge clk) begin
            full_step <= divide_two(remainder_full[stage], quotient[stage], denominator[stage]);
            low_step <= divide_two(remainder_low[stage], quotient_low[stage], denominator[stage]);
            denominator_step <= denominator[stage];
            size_step <= operand_size[stage];
        end
        assign {remainder_full[stage+1], quotient[stage+1]} = full_step;
        assign {remainder_low[stage+1], quotient_low[stage+1]} = low_step;
        assign denominator[stage+1] = denominator_step;
        assign operand_size[stage+1] = size_step;
    end endgenerate

    // Preserve the pinned native ALU exactly: its remainder uses A[7:0],
    // and its blocking flags assignment tests V before assigning V (thus 0).
    // Native division by zero leaves result undefined; only flags are defined.
    assign result = denominator[8] == 0 ? 16'hxxxx :
                    {remainder_low[8][7:0], quotient[8][7:0]};
    assign flags[0] = denominator[8] != 0 &&
                     (operand_size[8] ? result == 0 : result[7:0] == 0);
    assign flags[1] = 1'b0;
    assign flags[2] = denominator[8] == 0 || quotient[8][15:8] != 0;
    assign flags[3] = denominator[8] == 0 || result[7];
endmodule
