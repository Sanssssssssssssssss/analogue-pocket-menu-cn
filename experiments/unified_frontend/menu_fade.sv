// SPDX-License-Identifier: MIT
// Offline candidate only: not connected to a game core or released bitstream.
module menu_fade (
    input wire clk, reset, frame_tick,
    input wire enabled, requested_visible,
    input wire [23:0] pixel,
    output reg [3:0] level=0,
    output wire blank,
    output wire [23:0] gained_pixel
);
    // frame_tick must occur in vertical blank. The writer must wait for blank
    // before modifying a shared framebuffer, and request visibility only after
    // the complete upload has drained. enabled=0 bypasses game pixels unchanged.
    always @(posedge clk) begin
        if(reset || !enabled)level<=0;
        else if(frame_tick)begin
            if(requested_visible && level<8)level<=level+1'b1;
            else if(!requested_visible && level>0)level<=level>=2 ? level-2'd2 : 4'd0;
        end
    end
    wire [3:0] gain=enabled ? level : 4'd8;
    (* multstyle="logic" *) wire [11:0] red_gain=pixel[23:16]*gain;
    (* multstyle="logic" *) wire [11:0] green_gain=pixel[15:8]*gain;
    (* multstyle="logic" *) wire [11:0] blue_gain=pixel[7:0]*gain;
    assign gained_pixel={red_gain[10:3],green_gain[10:3],blue_gain[10:3]};
    assign blank=enabled && level==0;
endmodule
