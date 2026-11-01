// SPDX-License-Identifier: MIT
// One read-only request per VM arm. Command completion does not imply VM re-entry.
module runtime_request (
    input wire clk, power_reset, run_reset_n, in_menu,
    input wire [15:0] buttons,
    input wire [31:0] address, write_data,
    input wire write, ack, done,
    input wire [2:0] error,
    output reg request_read=0, request_open=0,
    output reg [31:0] read_data
);
    reg [15:0] keys_meta=0, keys=0;
    reg [1:0] mode=0, choice=0;
    reg released=0, fired=0, ack_seen=0, done_seen=0, done_low=0;
    reg [2:0] last_error=0;
    reg [31:0] count=0;
    always @(posedge clk) begin
        keys_meta<=buttons; keys<=keys_meta;
        request_read<=0; request_open<=0;
        if (power_reset) begin
            keys_meta<=0; keys<=0; mode<=0; choice<=0; released<=0;
            fired<=0; ack_seen<=0; done_seen<=0; done_low<=0;
            last_error<=0; count<=0;
        end else if (write && address==32'h60000030) begin
            mode<=write_data==1 ? 2'd1 : write_data==2 ? 2'd2 : 2'd0;
            choice<=0; released<=0; fired<=0; ack_seen<=0; done_seen<=0;
            done_low<=0; last_error<=0; count<=0;
        end else begin
            if (!run_reset_n || in_menu) released<=0;
            else if (mode!=0 && !fired) begin
                if (keys[5:4]==0) released<=1;
                if (released && (keys[5:4]==1 || keys[5:4]==2)) begin
                    choice<=keys[5:4]; fired<=1; count<=count+1'b1;
                    request_read<=mode==1; request_open<=mode==2;
                end
            end
            if (fired && !done_seen) begin
                if (ack) ack_seen<=1;
                // SDK retains done until its next operation: discard that old response.
                if (!done) done_low<=1;
                if (done_low && done) begin done_seen<=1; last_error<=error; end
            end
        end
    end
    always @* begin
        case (address)
            32'h60000030: read_data={30'd0,mode};
            32'h60000034,32'h600000B8: read_data={30'd0,choice};
            32'h600000B0: read_data={14'd0,mode,5'd0,last_error,4'd0,done_seen,ack_seen,fired,(mode!=0)};
            32'h600000B4: read_data=count;
            // /Assets/routetest/common/probe.dat, NUL padded to 256 bytes.
            32'hF3000000: read_data=32'h2F417373;
            32'hF3000004: read_data=32'h6574732F;
            32'hF3000008: read_data=32'h726F7574;
            32'hF300000C: read_data=32'h65746573;
            32'hF3000010: read_data=32'h742F636F;
            32'hF3000014: read_data=32'h6D6D6F6E;
            32'hF3000018: read_data=32'h2F70726F;
            32'hF300001C: read_data=32'h62652E64;
            32'hF3000020: read_data=32'h61740000;
            // Includes operation flags at +0x100 and size at +0x104: both zero.
            default: read_data=0;
        endcase
    end
endmodule
