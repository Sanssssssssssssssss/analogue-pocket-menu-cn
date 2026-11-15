// SPDX-License-Identifier: MIT
// Require a complete, matching cartridge envelope before applying an APF Memory.
module gba_state_guard #(
    parameter [31:0] STATE_BYTES = 32'h60d18,
    parameter [28:0] LOAD_TIMEOUT = 29'd445500000
) (
    input wire clk, enabled, capture_active, restore_active, staging_clear,
    input wire [79:0] game_id,
    input wire bridge_wr, bridge_rd, bridge_endian_little,
    input wire [31:0] bridge_addr, bridge_wr_data,
    input wire load_request,
    output wire load_valid,
    output wire payload_wr, payload_rd,
    output wire [31:0] payload_addr,
    output wire [31:0] envelope_data,
    output wire envelope_read,
    output reg reset_staging = 0,
    output wire receiving
);
    localparam [31:0] BASE = 32'h40000000;
    localparam [31:0] HEADER_BYTES = 16;
    localparam [31:0] END_ADDRESS = BASE + HEADER_BYTES + STATE_BYTES;
    localparam [31:0] MAGIC = 32'h504c4701;
    localparam [15:0] ENGINE_ABI = 16'h0001;

    function automatic [31:0] swap32(input [31:0] word);
        swap32 = {word[7:0],word[15:8],word[23:16],word[31:24]};
    endfunction

    wire in_envelope = bridge_addr >= BASE && bridge_addr < BASE + HEADER_BYTES;
    wire in_payload = bridge_addr >= BASE + HEADER_BYTES && bridge_addr < END_ADDRESS;
    wire [31:0] word_in = bridge_endian_little ? swap32(bridge_wr_data) : bridge_wr_data;
    reg [31:0] word_expected;
    always @(*) begin
        case (bridge_addr[3:2])
            0: word_expected = MAGIC;
            1: word_expected = game_id[79:48];
            2: word_expected = game_id[47:16];
            3: word_expected = {game_id[15:0], ENGINE_ABI};
        endcase
    end

    reg [16:0] next_word = 0;
    localparam [16:0] END_WORD = (HEADER_BYTES + STATE_BYTES) >> 2;
    reg [28:0] timeout_count = 0;
    reg accepted = 0, saw_restore = 0;
    reg prev_load = 0;
    wire load_rise = load_request && !prev_load;
    wire has_frame = next_word != 0;
    wire written = bridge_wr && (in_envelope || in_payload);
    wire aligned = bridge_addr[1:0] == 0;
    wire sequential = aligned && bridge_addr[18:2] == next_word;
    wire eligible = enabled && !capture_active && !restore_active && !accepted &&
                    !reset_staging && !staging_clear;
    wire valid_word = eligible && has_frame && written && sequential &&
                     (!in_envelope || word_in == word_expected);
    assign payload_wr = valid_word && in_payload;
    assign payload_rd = enabled && capture_active && bridge_rd && in_payload;
    assign payload_addr = bridge_addr - HEADER_BYTES;
    assign envelope_data = bridge_endian_little ? swap32(word_expected) : word_expected;
    assign envelope_read = enabled && capture_active && in_envelope;
    assign receiving = has_frame && !accepted;
    assign load_valid = enabled && (accepted || (eligible && next_word==END_WORD));

    always @(posedge clk) begin
        prev_load <= load_request;
        if (!enabled) begin
            next_word <= 0;
            timeout_count <= 0;
            accepted <= 0;
            saw_restore <= 0;
            reset_staging <= 0;
        end else if (reset_staging) begin
            if (staging_clear) reset_staging <= 0;
        end else if (load_rise && eligible) begin
            if (next_word == END_WORD) begin
                accepted <= 1;
                saw_restore <= 0;
            end
            else begin
                next_word <= 0;
                reset_staging <= has_frame;
            end
        end else if (accepted) begin
            if (restore_active) saw_restore <= 1;
            else if (saw_restore && !load_request) begin
                next_word <= 0;
                accepted <= 0;
                saw_restore <= 0;
            end
        end else if (eligible && written) begin
            timeout_count <= 0;
            if (!has_frame && bridge_addr==BASE && word_in==MAGIC) next_word<=1;
            else if (valid_word) next_word <= next_word + 1'b1;
            else begin
                next_word <= 0;
                reset_staging <= has_frame;
            end
        end else if (receiving) begin
            if (timeout_count >= LOAD_TIMEOUT) begin
                next_word <= 0;
                reset_staging <= 1;
            end else timeout_count <= timeout_count + 1'b1;
        end
    end
endmodule
