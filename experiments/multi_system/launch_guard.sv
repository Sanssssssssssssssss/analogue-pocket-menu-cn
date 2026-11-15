// SPDX-License-Identifier: MIT
// Read-only command sequencing experiment. Does NOT start a CPU or write saves.
// param_ready means the platform adapter has published an immutable filename
// structure; save_safe must only be asserted after real save/RTC flushing.
module launch_guard #(
    parameter integer TIMEOUT = 256
) (
    input wire clk, reset, start,
    input wire [1:0] platform,
    input wire [31:0] rom_bytes,
    input wire param_ready, save_safe,
    output reg busy, open_request, read_request, load_verified,
    output reg [3:0] error,
    output reg [15:0] slot,
    output reg [31:0] address, length,
    input wire command_ack, command_done,
    input wire [2:0] command_error
);
    localparam IDLE=0, BARRIER=1, OPEN_ACK=2, OPEN_DONE=3,
               READ_ISSUE=4, READ_ACK=5, READ_DONE=6;
    reg [2:0] state;
    reg [$clog2(TIMEOUT+1)-1:0] timer;
    reg done_before;
    wire done_edge = command_done && !done_before;
    task automatic fail(input [3:0] code);
        error <= code; busy <= 0; state <= IDLE;
    endtask
    always @(posedge clk) begin
        done_before <= command_done;
        open_request <= 0; read_request <= 0; load_verified <= 0;
        if (reset) begin
            state <= IDLE; busy <= 0; error <= 0; timer <= 0;
            slot <= 0; address <= 0; length <= 0; done_before <= 0;
        end else if (busy && timer == TIMEOUT-1) begin
            fail(4); // timeout; never hand partial data to the game
        end else begin
            if (busy) timer <= timer + 1'b1;
            case (state)
            IDLE: if (start) begin
                error <= 0; timer <= 0;
                if (platform == 2) fail(3); // SNES requires its host Chip32 loader
                else if (platform > 2 || rom_bytes == 0 ||
                    rom_bytes > (platform == 0 ? 32'h02000000 : 32'h01000000)) fail(2);
                else begin
                    slot <= platform == 0 ? 16'd1 : 16'd0;
                    address <= 32'h10000000;
                    length <= rom_bytes;
                    busy <= 1; state <= BARRIER;
                end
            end
            BARRIER: if (param_ready && save_safe) begin
                open_request <= 1; state <= OPEN_ACK; timer <= 0;
            end
            OPEN_ACK: if (command_ack) begin
                if (done_edge) begin
                    if (command_error != 0) fail(1);
                    else state <= READ_ISSUE;
                end else state <= OPEN_DONE;
                timer <= 0;
            end
            OPEN_DONE: if (done_edge) begin
                if (command_error != 0) fail(1);
                else state <= READ_ISSUE;
                timer <= 0;
            end
            READ_ISSUE: begin
                read_request <= 1; state <= READ_ACK; timer <= 0;
            end
            READ_ACK: if (command_ack) begin
                if (done_edge) begin
                    if (command_error != 0) fail(1);
                    else begin load_verified <= 1; busy <= 0; state <= IDLE; end
                end else state <= READ_DONE;
                timer <= 0;
            end
            READ_DONE: if (done_edge) begin
                if (command_error != 0) fail(1);
                else begin load_verified <= 1; busy <= 0; state <= IDLE; end
                timer <= 0;
            end
            default: fail(2);
            endcase
        end
    end
endmodule
