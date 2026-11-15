// SPDX-License-Identifier: MIT
// Hold the raw APF command until admission; publish one completed UI operation.
// Unlike the older framework helper, this upstream interface uses an ack and a
// one-cycle done pulse. Parameters remain stable through both phases.
module sega_menu_target (
    input wire clk,ready,
    input wire read_request,write_request,open_request,flush_request,
    input wire [15:0] slot,
    input wire [31:0] offset,address,length,
    output reg complete=1,
    output reg [2:0] error=0,
    output reg raw_request=0,
    output reg [15:0] raw_command=0,
    output reg [31:0] p0=0,p1=0,p2=0,p3=0,
    input wire raw_ack,raw_done,
    input wire [15:0] raw_result
);
    reg [1:0] state=0;
    always @(posedge clk)begin
        if(!ready)begin state<=0;raw_request<=0;complete<=1;error<=0;end
        else case(state)
            0:if(read_request || write_request || open_request || flush_request)begin
                complete<=0;error<=0;raw_request<=1;p0<={16'd0,slot};
                if(open_request)begin raw_command<=16'h0192;p1<=32'hF3000000;p2<=0;p3<=0;end
                else if(flush_request)begin raw_command<=16'h0188;p1<=0;p2<=0;p3<=0;end
                else begin raw_command<=read_request ? 16'h0180:16'h0184;p1<=offset;p2<=address;p3<=length;end
                state<=1;
            end
            1:if(raw_ack)begin raw_request<=0;state<=2;end
            2:if(raw_done)begin error<=raw_result>7 ? 3'd7:raw_result[2:0];complete<=1;state<=0;end
            default:begin state<=0;raw_request<=0;end
        endcase
    end
endmodule
