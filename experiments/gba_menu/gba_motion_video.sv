// SPDX-License-Identifier: MIT
// GBA menu-only transition candidate. The original 18-bit game framebuffer and
// raster are retained. Cache only the three old covers plus monochrome title;
// menu RGB565 -> cache RGB565 is lossless. No additional whole-page framebuffer.
module video_adapter (
    input wire clk_sys,clk_vid,reset,
    input wire menu_show,menu_fault,menu_active,menu_motion,menu_forward,
    output wire menu_visible,
    input wire [15:0] pixel_addr,
    input wire [17:0] pixel_data,
    input wire pixel_we,
    output reg [23:0] video_rgb=0,
    output reg video_de=0,video_vs=0,video_hs=0,video_skip=0
);
    reg [17:0] framebuffer[0:38399];
    always @(posedge clk_sys) if(pixel_we && pixel_addr<38400)framebuffer[pixel_addr]<=pixel_data;
    reg vid_ce=0;
    reg [8:0] h_count=0;
    reg [7:0] v_count=0;
    always @(posedge clk_vid) begin
        if(reset)begin vid_ce<=0;h_count<=0;v_count<=0;end
        else begin
            vid_ce<=~vid_ce;
            if(vid_ce)begin
                if(h_count==307)begin h_count<=0;v_count<=v_count==227 ? 8'd0:v_count+1'b1;end
                else h_count<=h_count+1'b1;
            end
        end
    end
    wire active=h_count<240 && v_count<160;
    wire hs_region=h_count>=250 && h_count<270;
    wire vs_region=v_count>=165 && v_count<170;
    wire frame_tick=vid_ce && h_count==0 && v_count==165;
    reg [2:0] show_sync=0,fault_sync=0,own_sync=0,motion_sync=0,forward_sync=0;
    reg show_frame=0,fault_frame=0,have_cache=0,hold_old=0,animating=0,forward=1;
    reg [3:0] step=0;
    function automatic [8:0] distance(input [3:0] n);
        case(n)
            0:distance=9;1:distance=35;2:distance=74;3:distance=120;
            4:distance=166;5:distance=205;6:distance=231;default:distance=240;
        endcase
    endfunction
    always @(posedge clk_vid) begin
        show_sync<={show_sync[1:0],menu_show};fault_sync<={fault_sync[1:0],menu_fault};
        own_sync<={own_sync[1:0],menu_active};motion_sync<={motion_sync[1:0],menu_motion};
        forward_sync<={forward_sync[1:0],menu_forward};
        if(reset)begin show_frame<=0;fault_frame<=0;have_cache<=0;hold_old<=0;animating<=0;step<=0;end
        else begin
          if(snapshot && active_d1 && x_q==239 && y_q==159)have_cache<=1;
          if(frame_tick)begin
            fault_frame<=fault_sync[2];
            if(!own_sync[2] || !motion_sync[2])begin
                show_frame<=show_sync[2];have_cache<=0;hold_old<=0;animating<=0;step<=0;
            end else if(!show_sync[2])begin
                // This acknowledgement permits writing the main framebuffer;
                // the completed old covers remain visible from the small cache.
                show_frame<=0;hold_old<=have_cache;animating<=0;
            end else if(!show_frame)begin
                show_frame<=1;forward<=forward_sync[2];
                if(hold_old && have_cache)begin animating<=1;step<=0;end
                else begin hold_old<=0;animating<=0;end
            end else if(animating)begin
                if(step==7)begin animating<=0;hold_old<=0;end else step<=step+1'b1;
            end else hold_old<=0;
          end
        end
    end
    // Protocol acknowledgement: incoming upload is writable only when false;
    // navigation resumes after the whole transition, preventing cache overwrite.
    assign menu_visible=(show_frame && !animating) || fault_frame;
    wire cache_enabled=own_sync[2] && motion_sync[2];
    wire transition=cache_enabled && (hold_old || animating);
    wire [8:0] delta=animating ? distance(step):9'd0;
    wire old_region=forward ? h_count<240-delta : h_count>=delta;
    wire [8:0] old_x=forward ? h_count+delta : h_count-delta;
    wire [8:0] new_x=!transition ? h_count : forward ? h_count+delta-240 : h_count+240-delta;
    wire use_old=transition && old_region;
    wire [15:0] read_addr=v_count*16'd240+new_x;
    reg [17:0] pixel_read=0;
    always @(posedge clk_vid) if(active && (!transition || !use_old))pixel_read<=framebuffer[read_addr];

    function automatic cover_at(input [8:0] x,input [7:0] y);
        cover_at=(x>=2 && x<50 && y>=35 && y<83) ||
                 (x>=72 && x<168 && y>=5 && y<101) ||
                 (x>=190 && x<238 && y>=35 && y<83);
    endfunction
    function automatic [13:0] cover_address(input [8:0] x,input [7:0] y);
        if(x<50)cover_address=(y-8'd35)*14'd48+x-2;
        else if(x<168)cover_address=14'd2304+(y-8'd5)*14'd96+x-72;
        else cover_address=14'd11520+(y-8'd35)*14'd48+x-190;
    endfunction
    // A single 13,824-word array rounds up to 16,384 words (32 M10Ks).
    // Three 4K banks plus one 2K bank use 28, within the available budget.
    wire [13:0] cache_write_address=cover_address(x_q,y_q);
    wire [13:0] cache_read_address=cover_address(old_x,v_count);
    wire cache_we=snapshot && active_d1 && cover_at(x_q,y_q);
    wire [15:0] cache_data={pixel_read[17:13],pixel_read[11:6],pixel_read[5:1]};
    wire [15:0] cache_bank_data[0:3];
    reg [1:0] cache_bank_q=0;
    always @(posedge clk_vid)cache_bank_q<=cache_read_address[13:12];
    genvar bank;
    generate for(bank=0;bank<4;bank=bank+1)begin:cache_banks
        localparam DEPTH=bank==3 ? 2048:4096;
        (* ramstyle="M10K,no_rw_check" *) reg [15:0] memory[0:DEPTH-1];
        reg [15:0] q=0;
        if(bank==3)begin
            always @(posedge clk_vid)begin
                if(cache_we && cache_write_address[13:12]==bank)memory[cache_write_address[10:0]]<=cache_data;
                q<=memory[cache_read_address[10:0]];
            end
        end else begin
            always @(posedge clk_vid)begin
                if(cache_we && cache_write_address[13:12]==bank)memory[cache_write_address[11:0]]<=cache_data;
                q<=memory[cache_read_address[11:0]];
            end
        end
        assign cache_bank_data[bank]=q;
    end endgenerate
    (* ramstyle="M10K,no_rw_check" *) reg old_title[0:7919];
    reg [17:0] title_color=0;
    reg [8:0] x_q=0;
    reg [7:0] y_q=0;
    reg active_d1=0,old_q=0,cover_q=0,title_q=0;
    wire [15:0] old_pixel=cache_bank_data[cache_bank_q];
    reg title_pixel=0;
    wire snapshot=cache_enabled && show_frame && !animating && !hold_old && !fault_frame;
    always @(posedge clk_vid) begin
        x_q<=h_count;y_q<=v_count;active_d1<=active;old_q<=use_old;
        cover_q<=cover_at(old_x,v_count);title_q<=old_x<240 && v_count>=108 && v_count<141;
        if(old_x<240 && v_count>=108 && v_count<141)title_pixel<=old_title[(v_count-8'd108)*16'd240+old_x];
        if(snapshot && active_d1)begin
            if(y_q>=108 && y_q<141)begin
                old_title[(y_q-8'd108)*16'd240+x_q]<=|pixel_read;
                if(|pixel_read)title_color<=pixel_read;
            end
        end
        if(reset)begin active_d1<=0;old_q<=0;end
    end
    wire [17:0] cached=cover_q ? {old_pixel[15:11],old_pixel[15],old_pixel[10:5],old_pixel[4:0],old_pixel[4]} :
                             title_q && title_pixel ? title_color:18'd0;
    wire [17:0] display_pixel=old_q ? cached:pixel_read;
    wire [23:0] expanded={display_pixel[17:12],display_pixel[17:16],display_pixel[11:6],display_pixel[11:10],display_pixel[5:0],display_pixel[5:4]};
    reg [63:0] error_bitmap[0:239];
    initial $readmemh("gba_menu_error.hex",error_bitmap);
    reg [63:0] error_column=0;
    reg [7:0] error_y=0;
    wire error_pixel=error_y>=48 && error_y<112 && error_column[error_y-48];
    reg [1:0] hs_pipe=0,vs_pipe=0;
    always @(posedge clk_vid) begin
        error_column<=error_bitmap[h_count<240 ? h_count:9'd0];error_y<=v_count;
        if(reset)begin hs_pipe<=0;vs_pipe<=0;video_rgb<=0;video_de<=0;video_vs<=0;video_hs<=0;video_skip<=0;end
        else begin
            hs_pipe<={hs_pipe[0],hs_region};vs_pipe<={vs_pipe[0],vs_region};
            video_rgb<=!active_d1 ? 24'd0 : fault_frame ? (error_pixel ? 24'he8e6dd:24'd0) :
                show_frame || (cache_enabled && hold_old) ? expanded:24'd0;
            video_de<=active_d1;video_hs<=hs_pipe[0] && !hs_pipe[1];video_vs<=vs_pipe[0] && !vs_pipe[1];video_skip<=!vid_ce;
        end
    end
endmodule
