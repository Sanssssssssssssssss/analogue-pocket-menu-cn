// SPDX-License-Identifier: MIT
module gb_rom_cheats (
    input wire clk, clear,
    input wire [128:0] code,
    input wire enabled, rom_read,
    input wire [14:0] address,
    input wire [7:0] data_in,
    output wire [7:0] data_out
);
    reg [15:0] valid=0;
    reg [4:0] count=0;
    reg [14:0] addresses[0:15];
    reg [7:0] compares[0:15], replacements[0:15];
    reg [15:0] compare_enabled;
    always @(posedge clk) begin
        if(clear)begin valid<=0;count<=0;end
        else if(code[128] && count<16)begin
            addresses[count[3:0]]<=code[78:64];
            compares[count[3:0]]<=code[39:32];
            replacements[count[3:0]]<=code[7:0];
            compare_enabled[count[3:0]]<=code[96];
            valid[count[3:0]]<=1;
            count<=count+1'b1;
        end
    end

    reg match_found;
    reg [7:0] replacement;
    integer index;
    always @* begin
        match_found=0;
        replacement=data_in;
        for(index=15;index>=0;index=index-1)begin
            if(valid[index] && address==addresses[index] &&
               (!compare_enabled[index] || data_in==compares[index]))begin
                match_found=1;
                replacement=replacements[index];
            end
        end
    end
    assign data_out=enabled && rom_read && match_found ? replacement : data_in;
endmodule
