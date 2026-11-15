// SPDX-License-Identifier: MIT
// APF DWORD FIFO to the upstream SDRAM byte request/ack interface.
// One complete byte retires only after the SDRAM busy handshake.
module sv_rom_loader (
    input wire clk_bridge,clk_memory,ready,start,active,
    input wire bridge_wr,bridge_endian_little,
    input wire [31:0] bridge_addr,bridge_wr_data,
    output reg [24:0] address=0,
    output reg [7:0] data=0,
    output reg write_en=0,
    input wire busy,
    output wire idle,
    output reg [31:0] bytes_written=0,
    output reg overflow=0
);
    wire clear=!ready || start;
    reg previous_wr=0,wrreq=0,rdreq=0;
    reg [59:0] fifo_in=0;
    wire [59:0] fifo_out;
    wire full,empty;
    reg [31:0] expected_address=0;
    wire accept=bridge_wr && !previous_wr && active && bridge_addr[31:28]==0;
    always @(posedge clk_bridge) begin
        previous_wr<=bridge_wr;wrreq<=0;
        if(clear)begin overflow<=0;expected_address<=0;end
        else if(accept)begin
            if(full || bridge_addr!=expected_address)overflow<=1;
            else begin
                fifo_in<={bridge_addr[27:0],bridge_endian_little ? bridge_wr_data:
                    {bridge_wr_data[7:0],bridge_wr_data[15:8],bridge_wr_data[23:16],bridge_wr_data[31:24]}};
                wrreq<=1;expected_address<=expected_address+4;
            end
        end
    end
    dcfifo #(.intended_device_family("Cyclone V"),.lpm_type("dcfifo"),
        .lpm_width(60),.lpm_numwords(32),.lpm_widthu(5),.lpm_showahead("OFF"),
        .overflow_checking("ON"),.underflow_checking("ON"),
        .rdsync_delaypipe(5),.wrsync_delaypipe(5),.use_eab("ON")) fifo(
        .aclr(clear),.wrclk(clk_bridge),.wrreq(wrreq && !clear),.data(fifo_in),.wrfull(full),
        .rdclk(clk_memory),.rdreq(rdreq && !clear),.q(fifo_out),.rdempty(empty));
    reg [2:0] state=0;
    reg [1:0] byte_index=0;
    reg [31:0] word_data=0;
    reg [2:0] active_sync=0;
    assign idle=empty && state==0 && !write_en && !busy;
    always @(posedge clk_memory or posedge clear)begin
        if(clear)begin
            state<=0;byte_index<=0;word_data<=0;address<=0;data<=0;
            rdreq<=0;write_en<=0;bytes_written<=0;active_sync<=0;
        end else begin
            active_sync<={active_sync[1:0],active};rdreq<=0;write_en<=0;
            case(state)
                0:if(active_sync[2] && !empty && !busy)begin rdreq<=1;state<=1;end
                1:state<=2;
                2:begin address<=fifo_out[56:32];word_data<=fifo_out[31:0];byte_index<=0;state<=3;end
                3:if(!busy)begin data<=word_data[7:0];write_en<=1;state<=4;end
                4:if(busy)state<=5;
                5:if(!busy)begin
                    bytes_written<=bytes_written+1'b1;
                    if(byte_index==3)state<=0;
                    else begin byte_index<=byte_index+1'b1;word_data<={8'd0,word_data[31:8]};address<=address+1'b1;state<=3;end
                end
                default:state<=0;
            endcase
        end
    end
endmodule
