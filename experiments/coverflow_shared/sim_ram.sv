// SPDX-License-Identifier: MIT
// Simulation only. Checked against actual Intel altsyncram in tb_ram.sv.
// Mixed-port same-address write/read collisions remain undefined, as upstream.
module coverflow_sim_ram #(parameter WIDTH=16,ADDR=8,DEPTH=(1<<ADDR),INIT="UNUSED")(
    input wire wclk,we,input wire [ADDR-1:0] waddr,input wire [WIDTH-1:0] wdata,
    input wire rclk,rce,input wire [ADDR-1:0] raddr,output wire [WIDTH-1:0] q
);
    reg [WIDTH-1:0] words[0:DEPTH-1];reg [ADDR-1:0] read_address=0;integer i;
    initial begin
        for(i=0;i<DEPTH;i=i+1)words[i]=0;
        if(INIT!="UNUSED")$readmemh(INIT,words);
    end
    always @(posedge wclk)if(we)words[waddr]<=wdata;
    always @(posedge rclk)if(rce)read_address<=raddr;
    assign q=words[read_address];
endmodule

`ifndef CF_RAM_VALIDATE
module picker_dpram #(parameter WIDTH=16,ADDR=8,DEPTH=(1<<ADDR),INIT="UNUSED")(
    input wire wclk,we,input wire [ADDR-1:0] waddr,input wire [WIDTH-1:0] wdata,
    input wire rclk,input wire [ADDR-1:0] raddr,output wire [WIDTH-1:0] q
);
    coverflow_sim_ram #(.WIDTH(WIDTH),.ADDR(ADDR),.DEPTH(DEPTH),.INIT(INIT)) ram(.*,.rce(1'b1));
endmodule
module coverflow_dpram_ce #(parameter WIDTH=16,ADDR=8,DEPTH=(1<<ADDR),INIT="UNUSED")(
    input wire wclk,we,input wire [ADDR-1:0] waddr,input wire [WIDTH-1:0] wdata,
    input wire rclk,rce,input wire [ADDR-1:0] raddr,output wire [WIDTH-1:0] q
);
    coverflow_sim_ram #(.WIDTH(WIDTH),.ADDR(ADDR),.DEPTH(DEPTH),.INIT(INIT)) ram(.*);
endmodule
`endif
