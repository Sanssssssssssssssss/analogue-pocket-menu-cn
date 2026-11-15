// SPDX-License-Identifier: MIT
// Add runtime target commands to JTFRAME's SPI bus, alongside its host commands.
module cps2_target (
    input wire clk, running, reset_enter,
    input wire [31:0] address, host_data, open_parameter,
    input wire host_write,
    output reg read_selected,
    output reg [31:0] read_data,
    input wire request,
    input wire [15:0] command,
    input wire [31:0] p0, p1, p2, p3,
    output reg ack=0, done=0,
    output reg [15:0] result=0
);
    reg [31:0] target_word=32'h636d0140;
    reg [31:0] params[0:3];
    reg setup_pending=1;
    reg active=0;
    wire status_write=host_write && address[31:24]==8'hf8 && address[15:0]==16'h1000;
    wire response=status_write && host_data[31:16]==16'h6f6b;
    wire busy=status_write && host_data[31:16]==16'h6275;

    always @* begin
        read_selected=1;
        casez(address)
            32'hf8??1000: read_data=target_word;
            32'hf8??1004: read_data=32'h20;
            32'hf8??1008: read_data=32'h40;
            32'hf8??102?: read_data=params[address[3:2]];
            32'hf3??????: read_data=open_parameter;
            default: begin read_selected=0;read_data=0;end
        endcase
    end

    always @(posedge clk) begin
        ack<=0;
        done<=0;
        if (reset_enter) begin
            active<=0;
            if (!setup_pending) target_word<=0;
        end else if (response && (setup_pending || active)) begin
            target_word<=host_data;
            setup_pending<=0;
            active<=0;
            if (active) begin result<=host_data[15:0];done<=1;end
        end else if (busy && (setup_pending || active)) begin
            // Keep the host's in-progress status visible until its final reply.
            target_word<=host_data;
        end else if (request && running && !setup_pending && !active) begin
            params[0]<=p0;
            params[1]<=p1;
            params[2]<=p2;
            params[3]<=p3;
            target_word<={16'h636d,command};
            active<=1;
            ack<=1;
        end
    end
endmodule
