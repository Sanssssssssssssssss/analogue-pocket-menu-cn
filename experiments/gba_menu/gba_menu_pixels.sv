// SPDX-License-Identifier: MIT
// Stream a complete menu into the existing GBA framebuffer; no second framebuffer.
module gba_menu_pixels (
    input wire clk_bridge, clk_memory,
    input wire bridge_wr, bridge_endian_little,
    input wire [31:0] bridge_addr, bridge_wr_data,
    input wire menu_owned, frame_request,
    input wire [15:0] game_pixel_addr,
    input wire game_pixel_we,
    output wire [15:0] pixel_addr,
    output wire [17:0] pixel_data,
    output wire pixel_we,
    output reg frame_ack=0,
    output reg frame_started=0,
    output reg frame_valid=0,
    output reg frame_fault=0,
    output reg game_frame_ready=0,
    output wire [15:0] received_pixels,
    output reg [15:0] bridge_words=0
);
    wire write_en;
    wire [27:0] write_addr;
    wire [15:0] write_data;
    data_loader #(.ADDRESS_MASK_UPPER_4(4'h5),.OUTPUT_WORD_SIZE(2),
                  .WRITE_MEM_CLOCK_DELAY(4)) pixels_in (
        .clk_74a(clk_bridge),.clk_memory(clk_memory),.bridge_wr(bridge_wr),
        .bridge_endian_little(bridge_endian_little),.bridge_addr(bridge_addr),
        .bridge_wr_data(bridge_wr_data),.write_en(write_en),
        .write_addr(write_addr),.write_data(write_data));
    reg [2:0] request_sync=0;
    reg request_seen=0, collecting=0, game_started=0;
    reg [15:0] next_pixel=0;
    reg request_seen_bridge=0,previous_bridge_wr=0;
    always @(posedge clk_bridge) begin
        previous_bridge_wr<=bridge_wr;
        if(frame_request!=request_seen_bridge)begin
            request_seen_bridge<=frame_request;bridge_words<=0;
        end else if(bridge_wr && !previous_bridge_wr && bridge_addr[31:28]==5)
            bridge_words<=bridge_words+1'b1;
    end
    assign received_pixels=frame_valid ? 16'd38400 : next_pixel;
    always @(posedge clk_memory) begin
        request_sync<={request_sync[1:0],frame_request};
        if (request_sync[2]!=request_seen) begin
            request_seen<=request_sync[2];frame_started<=request_sync[2];frame_valid<=0;
            collecting<=1;next_pixel<=0;frame_fault<=0;
        end else if (write_en && menu_owned && collecting) begin
            if (write_addr!={11'd0,next_pixel,1'b0} || next_pixel>=38400) begin
                frame_fault<=1;frame_valid<=0;collecting<=0;
            end else if (next_pixel==38399) begin
                frame_ack<=request_seen;frame_valid<=1;collecting<=0;
            end else next_pixel<=next_pixel+1'b1;
        end
        if(menu_owned) begin game_frame_ready<=0;game_started<=0;end
        else if(game_pixel_we) begin
            if(game_pixel_addr==0)game_started<=1;
            if(game_pixel_addr==38399 && game_started)game_frame_ready<=1;
        end
    end
    assign pixel_addr=write_addr[16:1];
    assign pixel_data={write_data[15:11],write_data[15],write_data[10:5],write_data[4:0],write_data[4]};
    assign pixel_we=write_en && menu_owned && collecting &&
                    write_addr=={11'd0,next_pixel,1'b0} && next_pixel<38400;
endmodule
