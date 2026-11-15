// SPDX-License-Identifier: MIT
// This block stays clocked during the APF run reset; it never requests file I/O.
module route_probe #(
    parameter [31:0] ID = 32'h504C4100,
    parameter integer CYCLES_PER_MS = 74250
) (
    input wire clk, power_reset, run_reset_n,
    input wire [15:0] buttons,
    input wire [7:0] address,
    input wire write,
    input wire [31:0] write_data,
    output reg [31:0] read_data
);
    reg [15:0] keys_meta=0, keys=0;
    reg [31:0] uptime_ms=0, divider=0, phase=0, choice=0;
    reg [31:0] result=0, detail=0;
    reg [15:0] last_keys=0;
    reg released=0;
    always @(posedge clk) begin
        keys_meta <= buttons;
        keys <= keys_meta;
        if (power_reset) begin
            keys_meta<=0; keys<=0; uptime_ms<=0; divider<=0;
            phase<=0; choice<=0; released<=0;
            result<=0; detail<=0; last_keys<=0;
        end else begin
            if (keys!=0) last_keys<=keys;
            if (write && address==8'h20) result<=write_data;
            if (write && address==8'h24) detail<=write_data;
            if (divider==CYCLES_PER_MS-1) begin divider<=0; uptime_ms<=uptime_ms+1'b1; end
            else divider<=divider+1'b1;
            if (write && address==8'h10) begin
                phase<=write_data; choice<=0; released<=0;
            end else if (phase!=0 && choice==0) begin
                // Require release after arming; a button held from the OS cannot select.
                if (keys[5:4]==0) released<=1;
                if (released && keys[5:4]==1) choice<=1;
                if (released && keys[5:4]==2) choice<=2;
            end
        end
    end
    always @* begin
        case(address)
            8'h00: read_data=ID;
            8'h04: read_data={31'd0,run_reset_n};
            8'h08: read_data=uptime_ms;
            8'h0C: read_data={16'd0,keys};
            8'h10: read_data=phase;
            8'h14: read_data=choice;
            8'h1C: read_data={16'd0,last_keys};
            8'h20: read_data=result;
            8'h24: read_data=detail;
            // Core Settings may write back its readout address; aliases ignore writes.
            8'h90: read_data=phase;
            8'hA0: read_data=result;
            8'hA4: read_data=detail;
            default: read_data=0;
        endcase
    end
endmodule
