// SPDX-License-Identifier: MIT
// Standalone menu raster. RGB332 is used only for menu storage; game video bypasses it.
module menu_video (
    input wire clk_memory,clk_video,reset,
    input wire pixel_we,
    input wire [15:0] pixel_addr,
    input wire [17:0] pixel_data,
    input wire menu_owned,menu_show,menu_fault,
    input wire [23:0] game_rgb,
    input wire game_de,game_hs,game_vs,
    output wire menu_visible,
    output reg [23:0] rgb=0,
    output reg de=0,hs=0,vs=0
);
    (* ramstyle="M10K,no_rw_check" *) reg [7:0] pixels[0:38399];
    always @(posedge clk_memory) if(pixel_we && pixel_addr<38400)
        pixels[pixel_addr]<={pixel_data[17:15],pixel_data[11:9],pixel_data[5:4]};
    reg [8:0] x=0,y=0;
    reg [2:0] own_sync=7,show_sync=0,fault_sync=0;
    reg owned=1,shown=0,fault=0;
    wire frame_tick=x==0 && y==240;
    wire in_menu=x>=8 && x<248 && y>=40 && y<200;
    wire [15:0] address=(y-9'd40)*16'd240+(x-9'd8);
    reg [7:0] pixel=0;
    reg inside_q=0,de_q=0,hs_q=0,vs_q=0;
    reg [63:0] error_bitmap[0:239];
    initial $readmemh("gba_menu_error.hex",error_bitmap);
    reg [63:0] error_column=0;
    reg [7:0] error_y=0;
    wire error_pixel=error_y>=48 && error_y<112 && error_column[error_y-48];
    assign menu_visible=shown || fault;
    always @(posedge clk_video) begin
        own_sync<={own_sync[1:0],menu_owned};show_sync<={show_sync[1:0],menu_show};
        fault_sync<={fault_sync[1:0],menu_fault};
        if(reset)begin x<=0;y<=0;owned<=1;shown<=0;fault<=0;end
        else begin
            if(x==340)begin x<=0;y<=y==261 ? 9'd0:y+1'b1;end else x<=x+1'b1;
            if(frame_tick)begin owned<=own_sync[2];shown<=show_sync[2];fault<=fault_sync[2];end
        end
        if(in_menu)pixel<=pixels[address];
        inside_q<=in_menu;de_q<=x<256 && y<240;
        hs_q<=x==256;vs_q<=frame_tick;
        error_column<=error_bitmap[x>=8 && x<248 ? x-8 : 0];
        error_y<=y-40;
        if(owned)begin
            rgb<=!inside_q ? 24'd0 : fault ? (error_pixel ? 24'he8e6dd:24'd0) :
                 shown ? {{pixel[7:5],pixel[7:5],pixel[7:6]},
                          {pixel[4:2],pixel[4:2],pixel[4:3]},
                          {pixel[1:0],pixel[1:0],pixel[1:0],pixel[1:0]}} : 24'd0;
            de<=de_q;hs<=hs_q;vs<=vs_q;
        end else begin rgb<=game_rgb;de<=game_de;hs<=game_hs;vs<=game_vs;end
    end
endmodule
