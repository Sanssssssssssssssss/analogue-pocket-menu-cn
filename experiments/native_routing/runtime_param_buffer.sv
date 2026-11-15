// SPDX-License-Identifier: MIT
// BRIDGE reads transmit the previous strobed word; match the SDK register bank.
module runtime_param_buffer (
    input wire clk, read,
    input wire [31:0] address, value,
    output reg [31:0] data=0
);
    always @(posedge clk)
        if (read && address[31:16]==16'hF300) data<=value;
endmodule
