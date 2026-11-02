// SPDX-License-Identifier: MIT
// Ready/response memory adapter for the accepted CoverFlow's scanline geometry.
// RGB565 cache layout and source-coordinate arithmetic match cover_picker.sv.
module coverflow_line_fetch #(
    parameter CB=7,
    parameter [23:0] ART_WORD=0,
    parameter TIMEOUT=16384
) (
    input wire clk,enable,invalidate,
    input wire line_toggle,
    input wire [8:0] line_y,
    input wire signed [10:0] cover_x[0:3],
    input wire [7:0] cover_size[0:3],
    input wire [CB-1:0] cover_game[0:3],
    input wire cover_valid[0:3],
    input wire cover_loaded[0:3],
    output reg mem_req=0,
    output reg [23:0] mem_word_addr=0,
    input wire mem_done,
    input wire [31:0] mem_data,
    output wire mem_idle,
    output reg line_we=0,
    output reg [9:0] line_addr=0,
    output reg [15:0] line_data=0,
    output reg [9:0] ready_even=0,ready_odd=0,
    output reg underrun=0,fault=0
);
    localparam IDLE=0,SETUP=1,RUN=2,WAIT_DATA=3,DRAIN=4,SCALE=5,OFFSET=6,BASE=7,SELECT=8,CHECK=9;
    reg [3:0] state=IDLE;
    reg [2:0] line_sync=0;
    reg line_seen=0,new_line=0;
    reg [8:0] next_y=0,y=0;
    reg signed [10:0] x[0:3];reg [7:0] size[0:3];reg [CB-1:0] game[0:3];reg valid[0:3],loaded[0:3];
    reg [1:0] which=0;
    reg signed [10:0] active_x=0;
    reg [7:0] active_size=0;
    reg [CB-1:0] active_game=0;
    reg active_valid=0,active_loaded=0,eligible=0;
    reg [8:0] screen_x=0,end_x=0;
    reg [17:0] source_x=0;
    reg [9:0] source_step=0;
    reg [23:0] row_base=0;
    reg [23:0] slot_base=0;
    reg [7:0] source_row=0;
    reg [10:0] initial_x=0;
    reg [17:0] scaled_row=0;
    reg [14:0] row_offset=0;
    reg small_texture=0;
    wire [14:0] row_times_80={1'b0,scaled_row[15:8],6'd0}+{3'd0,scaled_row[15:8],4'd0};
    reg pending=0,pending_high=0,drop_pending=0;
    reg [23:0] pending_word=0;
    reg cached=0;
    reg [22:0] cached_addr=0;
    reg [31:0] cached_data=0;
    localparam TIMER_BITS=(TIMEOUT<2)?1:$clog2(TIMEOUT);
    reg [TIMER_BITS-1:0] timer=0;
    reg [9:0] step_lut[0:255];integer si;
    initial for(si=0;si<256;si=si+1)step_lut[si]=(si==0)?10'd256:(si<=80)?(80*256)/si:(128*256)/si;
    wire [23:0] address_now=row_base+source_x[17:8];
    wire line_arrived=line_sync[2]!=line_seen;
    assign mem_idle=!pending && !mem_req;
    integer i;
    task advance_pixel;
        begin screen_x<=screen_x+1'b1;source_x<=source_x+source_step;end
    endtask
    always @(posedge clk)begin
        line_sync<={line_sync[1:0],line_toggle};mem_req<=0;line_we<=0;
        if(line_arrived)begin
            line_seen<=line_sync[2];next_y<=line_y;new_line<=1;
            if(state!=IDLE)underrun<=1;
            if(line_y[0])ready_odd<=0;else ready_even<=0;
        end
        if(invalidate || !enable)begin
            cached<=0;ready_even<=0;ready_odd<=0;new_line<=0;
            if(pending)drop_pending<=1;
        end
        if(invalidate && !pending && !mem_req)begin fault<=0;underrun<=0;end
        if(pending)begin
            if(timer<TIMEOUT-1)timer<=timer+1'b1;
            if(timer==TIMEOUT-1)fault<=1;
        end
        if(mem_done && pending)begin
            pending<=0;cached<=enable && !drop_pending && !invalidate && !new_line && !line_arrived && !fault;
            cached_addr<=pending_word[23:1];cached_data<=mem_data;
            if(enable && !drop_pending && !new_line && !line_arrived && !invalidate && !fault)begin
                line_we<=1;line_addr<={y[0],screen_x};line_data<=pending_high ? mem_data[31:16]:mem_data[15:0];
                advance_pixel();state<=RUN;
            end else state<=IDLE;
        end
        if(!pending && !mem_req)begin
            if(!enable || fault || invalidate)begin state<=IDLE;new_line<=0;end
            else if(line_arrived)begin end
            else if(new_line)begin
                y<=next_y;which<=0;state<=SELECT;new_line<=0;cached<=0;
                if(next_y==0)for(i=0;i<4;i=i+1)begin
                    x[i]<=cover_x[i];size[i]<=cover_size[i];game[i]<=cover_game[i];valid[i]<=cover_valid[i];loaded[i]<=cover_loaded[i];
                end
            end else case(state)
                IDLE:begin end
                SELECT:begin
                    active_x<=x[which];active_size<=size[which];active_game<=game[which];
                    active_valid<=valid[which];active_loaded<=loaded[which];state<=SETUP;
                end
                SETUP:begin:setup
                    reg signed [11:0] ly,xs,xe;
                    reg [7:0] S,r,row;
                    S=active_size;r=(S*7)>>5;
                    ly=$signed({3'b0,y})-($signed(12'sd96)-$signed({5'b0,S[7:1]}));
                    xs=(active_x<0)?12'sd0:active_x;
                    xe=(active_x+$signed({4'b0,S})>12'sd320)?12'sd320:active_x+$signed({4'b0,S});
                    eligible<=active_valid && ly>=0 && ly<$signed({4'b0,S})+$signed({4'b0,r}) && xs<xe;
                    source_row<=(ly<$signed({4'b0,S}))?ly[7:0]:S-1'b1-(ly[7:0]-S);
                    source_step<=step_lut[S];small_texture<=S<=80;
                    slot_base<=ART_WORD+({{(24-CB){1'b0}},active_game}<<15);
                    initial_x<=xs-active_x;screen_x<=xs[8:0];end_x<=xe[8:0];state<=CHECK;
                end
                CHECK:if(eligible)state<=SCALE;else if(which==3)state<=DRAIN;else begin which<=which+1'b1;state<=SELECT;end
                // The reference's source-coordinate arithmetic is unchanged.
                // Registers separate its LUT, products, mip offset and address
                // addition so no full texture setup is required in one 10 ns cycle.
                SCALE:begin scaled_row<=source_row*source_step;source_x<=initial_x*source_step;state<=OFFSET;end
                OFFSET:begin row_offset<=small_texture ? 15'd16384+row_times_80:{scaled_row[15:8],7'd0};state<=BASE;end
                BASE:begin row_base<=slot_base+{9'd0,row_offset};state<=RUN;end
                RUN:begin
                    if(screen_x>=end_x)begin if(which==3)state<=DRAIN;else begin which<=which+1'b1;state<=SELECT;end end
                    else if(!active_loaded)begin line_we<=1;line_addr<={y[0],screen_x};line_data<=16'h2124;advance_pixel();end
                    else if(cached && cached_addr==address_now[23:1])begin
                        line_we<=1;line_addr<={y[0],screen_x};line_data<=address_now[0] ? cached_data[31:16]:cached_data[15:0];advance_pixel();
                    end else begin
                        mem_req<=1;mem_word_addr<=address_now;pending_word<=address_now;pending_high<=address_now[0];
                        pending<=1;drop_pending<=0;timer<=0;state<=WAIT_DATA;
                    end
                end
                WAIT_DATA:begin end
                DRAIN:begin
                    // Commit after the final RAM write has reached the line buffer.
                    if(y[0])ready_odd<={1'b1,y};else ready_even<={1'b1,y};
                    state<=IDLE;
                end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
