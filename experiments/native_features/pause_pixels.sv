// SPDX-License-Identifier: MIT
// A small resident pause/error screen in the existing 320x288 menu raster.
module native_pause_pixels (
    input wire clk, pixel_ce, frame_start,
    input wire [8:0] x, y,
    input wire [2:0] scene,
    output reg active = 0,
    output reg [23:0] rgb = 0
);
    reg [2:0] scene_meta = 0, scene_sync = 0, frame_scene = 0;
    always @(posedge clk) begin
        scene_meta <= scene;
        scene_sync <= scene_meta;
        if (frame_start && pixel_ce) frame_scene <= scene_sync;
    end

    wire heading = y >= 64 && y < 96;
    wire first = y >= 128 && y < 160;
    wire second = y >= 192 && y < 224;
    wire in_panel = x >= 16 && x < 304;
    wire in_text = x >= 32 && x < 288;
    wire selectable = frame_scene == 2 || frame_scene == 3;
    wire error_screen = frame_scene == 4 || frame_scene == 6;
    wire [8:0] text_x = x - 9'd32;
    reg [3:0] label_id;
    always @(*) begin
        label_id = 0;
        if (heading) begin
            case (frame_scene)
                1: label_id = 1;  // pausing
                2,3: label_id = 2;  // paused
                4,6: label_id = 3;  // failed
                5: label_id = 4;  // saving
                default: label_id = 0;
            endcase
        end else if (first) begin
            if (selectable) label_id = 5;  // continue
            else if (error_screen) label_id = 7;  // retry
        end else if (second) begin
            if (selectable) label_id = 6;  // save and return
            else if (frame_scene == 4) label_id = 8;  // return to game
            else if (frame_scene == 6) label_id = 9;  // back to library
        end
    end

    (* ramstyle = "MLAB" *) reg [15:0] bitmap [0:1279];
    initial $readmemh("native_pause.hex", bitmap);
    reg [15:0] glyph_column = 0;
    reg [3:0] glyph_row = 0;
    reg layer_s1 = 0, text_s1 = 0, selected_s1 = 0, option_s1 = 0;
    always @(posedge clk) if (pixel_ce) begin
        glyph_column <= bitmap[{label_id, text_x[7:1]}];
        glyph_row <= y[4:1];
        layer_s1 <= frame_scene != 0;
        text_s1 <= in_text && label_id != 0;
        selected_s1 <= in_panel && ((first && frame_scene == 2) || (second && frame_scene == 3));
        option_s1 <= in_panel && label_id != 0 && (first || second);
        active <= layer_s1;
        if (text_s1 && glyph_column[glyph_row]) rgb <= 24'hf5f6fa;
        else if (selected_s1) rgb <= 24'h294963;
        else if (option_s1) rgb <= 24'h141e29;
        else rgb <= 24'h080c12;
    end
endmodule
