// SPDX-License-Identifier: MIT
// This text is compiled into the core and remains visible without SD artwork.
module atari_error_pixels(input wire clk,de,hs,vs,skip,output wire [23:0] rgb);
    reg [31:0] columns[0:319];
    initial $readmemh("atari_error.hex",columns);
    reg [8:0] x=0,y=0;
    reg [31:0] column;
    always @(posedge clk)begin
        if(vs)y<=0;else if(hs)y<=y+1'b1;
        if(!de)x<=0;else if(!skip)x<=x==319 ? 0:x+1'b1;
        column<=columns[x<319 ? x+1'b1:0];
    end
    wire ink=y>=130 && y<162 && column[y-130];
    assign rgb=ink ? 24'heeeee8:24'h080a0c;
endmodule
