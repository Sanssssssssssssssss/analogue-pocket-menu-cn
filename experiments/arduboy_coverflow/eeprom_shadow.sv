// SPDX-License-Identifier: MIT
// Native EEPROM commits are mirrored at the same AVR edge. The APF bridge
// sees a complete DWORD after one 74MHz clock, before its fixed SPI capture.
module ard_eeprom_shadow(input wire clk_avr,clk_bridge,write_en,
    input wire [9:0] write_address,input wire [7:0] write_data,
    input wire [31:0] bridge_address,input wire bridge_endian_little,
    output wire [31:0] bridge_data);
    wire [7:0] q[0:3];
    // Use the already validated explicit Intel RAM primitive. An initialized
    // FF read register can prevent inference and consume 8192 fabric flops.
    // All 1024 bytes are restored and checked before NV size becomes nonzero.
    genvar lane;
    generate for(lane=0;lane<4;lane=lane+1)begin:bank
        picker_dpram #(.WIDTH(8),.ADDR(8),.DEPTH(256)) memory(
            .wclk(clk_avr),.we(write_en && write_address[1:0]==lane),
            .waddr(write_address[9:2]),.wdata(write_data),.rclk(clk_bridge),
            .raddr(bridge_address[9:2]),.q(q[lane]));
    end endgenerate
    assign bridge_data=bridge_endian_little ? {q[3],q[2],q[1],q[0]}:{q[0],q[1],q[2],q[3]};
endmodule
