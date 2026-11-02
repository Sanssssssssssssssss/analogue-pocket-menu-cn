// SPDX-License-Identifier: MIT
// One outstanding ready/response read across unrelated clocks. Address and
// response buses remain stable until their two-phase handshake is acknowledged.
module coverflow_memory_bridge(
    input wire source_clock,memory_clock,
    input wire source_request,
    input wire [23:0] source_word_address,
    output reg source_done=0,
    output reg [31:0] source_data=0,
    output wire source_idle,
    output reg source_fault=0,
    output reg memory_request=0,
    output reg [23:0] memory_word_address=0,
    input wire memory_done,
    input wire [31:0] memory_data
);
    reg request_toggle=0,source_pending=0;
    reg [23:0] held_address=0;
    reg [2:0] request_sync=0,response_sync=0;
    reg request_seen=0,response_seen=0,response_toggle=0,memory_pending=0;
    reg [31:0] held_response=0;
    assign source_idle=!source_pending && !source_request;
    always @(posedge source_clock)begin
        response_sync<={response_sync[1:0],response_toggle};source_done<=0;
        if(source_request)begin
            if(source_pending)source_fault<=1;
            else begin held_address<=source_word_address;request_toggle<=~request_toggle;source_pending<=1;end
        end
        if(response_sync[2]!=response_seen)begin
            response_seen<=response_sync[2];
            if(!source_pending)source_fault<=1;
            else begin source_data<=held_response;source_done<=1;source_pending<=0;end
        end
    end
    always @(posedge memory_clock)begin
        request_sync<={request_sync[1:0],request_toggle};memory_request<=0;
        if(request_sync[2]!=request_seen && !memory_pending)begin
            request_seen<=request_sync[2];memory_word_address<=held_address;memory_request<=1;memory_pending<=1;
        end
        if(memory_done && memory_pending)begin
            held_response<=memory_data;response_toggle<=~response_toggle;memory_pending<=0;
        end
    end
endmodule
