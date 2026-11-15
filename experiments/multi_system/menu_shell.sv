// SPDX-License-Identifier: MIT
// Portable Chinese page cache / navigation experiment. No game core is present.
// A platform adapter must service page_request and launch_request.
module menu_shell (
    input wire clk, reset,
    input wire [15:0] buttons,
    output reg page_request,
    output reg [2:0] page,
    input wire page_write,
    input wire [10:0] page_address,
    input wire [15:0] page_word,
    input wire page_commit,
    output reg page_ready,
    output reg launch_request,
    output reg [1:0] launch_platform, launch_entry,
    input wire launch_failed,
    output wire [23:0] rgb,
    output wire de, hs, vs,
    output reg [1:0] selected
);
    // Eight 256-column x 16-pixel text strips: 4 KiB, regenerated per page.
    (* ramstyle = "M10K" *) reg [15:0] text_columns [0:2047];
    reg [11:0] received;
    reg pending_commit;
    reg [15:0] button_meta, button_sync, previous_buttons;
    wire [15:0] pressed = button_sync & ~previous_buttons;
    reg [8:0] x, y;
    reg [4:0] line_y;
    reg [2:0] row;
    wire frame_start = x == 0 && y == 0;
    wire text_region = x >= 32 && x < 288 && y >= 16 && y < 208 && line_y < 16;
    wire [10:0] address = {row, 8'(x - 32)};
    reg [15:0] column;
    reg [3:0] bit_y;
    reg pixel_region, selected_pixel, de_q, hs_q, vs_q, ready_q;
    reg de_d, hs_d, vs_d, ready_d;
    reg [23:0] rgb_d;
    wire highlighted = page < 4 && row == {1'b0, selected}+3'd1;

    assign de = de_d;
    assign hs = hs_d;
    assign vs = vs_d;
    assign rgb = rgb_d;

    task automatic request_page(input [2:0] next_page);
        page <= next_page;
        page_request <= 1;
        page_ready <= 0;
        received <= 0;
        pending_commit <= 0;
        selected <= 0;
    endtask

    always @(posedge clk) begin
        button_meta <= buttons;
        button_sync <= button_meta;
        previous_buttons <= button_sync;
        page_request <= 0;
        launch_request <= 0;
        if (reset) begin
            x <= 0; y <= 0; row <= 0; line_y <= 0;
            button_meta <= 0; button_sync <= 0; previous_buttons <= 0;
            launch_platform <= 0; launch_entry <= 0;
            request_page(0);
        end else begin
            if (x == 399) begin
                x <= 0;
                y <= y == 261 ? 9'd0 : y + 9'd1;
                if (y == 15 || y == 261) begin row <= 0; line_y <= 0; end
                else if (y >= 16 && y < 207) begin
                    if (line_y == 23) begin row <= row + 3'd1; line_y <= 0; end
                    else line_y <= line_y + 5'd1;
                end
            end else x <= x + 9'd1;
            // Sequential writes only; incomplete or stale pages cannot become visible.
            if (page_write && !page_ready && !pending_commit && received < 2048 &&
                {1'b0,page_address} == received) begin
                text_columns[page_address] <= page_word;
                received <= received + 12'd1;
            end
            if (page_commit && received == 2048 && !page_ready) pending_commit <= 1;
            if (pending_commit && frame_start) begin page_ready <= 1; pending_commit <= 0; end
            if (page_ready) begin
                if (pressed[5]) request_page(0);
                else if (page < 4) begin
                    if (pressed[0]) selected <= selected == 0 ? 2'd2 : selected - 2'd1;
                    else if (pressed[1]) selected <= selected == 2 ? 2'd0 : selected + 2'd1;
                    else if (pressed[4]) begin
                        if (page == 0) request_page({1'b0,selected}+3'd1);
                        else begin
                            launch_platform <= 2'(page-1);
                            launch_entry <= selected;
                            launch_request <= 1;
                            request_page(4);
                        end
                    end
                end
            end
            if (launch_failed && page == 4) request_page(5);
        end
        // Pixel and sync pipeline have identical latency; no clock mux.
        column <= text_columns[address];
        bit_y <= line_y[3:0];
        pixel_region <= text_region;
        selected_pixel <= page_ready && highlighted && x >= 24 && x < 296 && y >= 40 && y < 112;
        de_q <= x < 320 && y < 240;
        hs_q <= x == 320;
        vs_q <= x == 0 && y == 240;
        ready_q <= page_ready;
        // Register the RAM-bit/color mux; keep DE/HS/VS on the same extra stage.
        rgb_d <= !ready_q || !de_q ? 24'h000000 :
                 pixel_region && column[bit_y] ? (selected_pixel ? 24'hf0d38b : 24'he2e8f0) :
                 selected_pixel ? 24'h152235 : 24'h000000;
        de_d <= de_q; hs_d <= hs_q; vs_d <= vs_q; ready_d <= ready_q;
    end
endmodule
