// SPDX-License-Identifier: MIT
// Bounded PLCH read-replacement records. Validate the complete file before
// emitting any code. RAM payload crosses clocks only while held for an ACK.
module native_cheat_loader #(
    parameter [15:0] PLATFORM = 16'd3,
    parameter integer MAX_CODES = 16,
    parameter integer ADDRESS_BITS = 16,
    parameter integer DATA_BITS = 8,
    parameter [31:0] MIN_ADDRESS = 32'h8000,
    parameter [31:0] MAX_ADDRESS = 32'hffff,
    parameter [31:0] BASE = 32'h90000000
) (
    input wire clk, clk_core, reset, receiving,
    input wire bridge_wr, bridge_endian_little,
    input wire [31:0] bridge_addr, bridge_wr_data,
    output reg ready=0, fault=0,
    output reg [128:0] code=0,
    output wire code_reset
);
    localparam WORDS = 12+4*MAX_CODES;
    (* ramstyle="M10K, no_rw_check" *) reg [31:0] memory[0:WORDS-1];
    reg [31:0] read_data;
    reg [6:0] read_address=0;
    wire [31:0] normalized=bridge_endian_little ? bridge_wr_data :
        {bridge_wr_data[7:0],bridge_wr_data[15:8],bridge_wr_data[23:16],bridge_wr_data[31:24]};
    wire ingress=receiving && bridge_wr && bridge_addr[31:12]==BASE[31:12];
    reg receiving_prev=0;
    reg [7:0] received=0;
    reg [5:0] count=0;
    reg [31:0] expected_crc=0, crc=32'hffffffff, word_data=0;
    reg [2:0] phase=0;
    reg [2:0] byte_index=0;
    reg [1:0] record_word=0;
    reg [31:0] record_flags=0,record_address=0,record_compare=0;
    reg [127:0] payload=0;
    reg send_toggle=0, ack_toggle=0;
    reg core_pending=0,pending_toggle=0;
    reg [2:0] ack_sync=0, send_sync=0, reset_sync=7;
    reg reset_prev=0,clear_toggle=0,clear_ack=0;
    reg [2:0] clear_sync=0,clear_ack_sync=0,core_clear_sync=7;
    localparam IDLE=0,WAIT_RAM=1,CAPTURE=2,CHECK_CRC=3,DISPATCH_WAIT=4,WAIT_CLEAR=5;
    reg playback=0;
    wire [7:0] total_words=8'd12+{count,2'b00};
    wire [31:0] address_mask=32'hffffffff >> (32-ADDRESS_BITS);
    wire [31:0] data_mask=32'hffffffff >> (32-DATA_BITS);
    function automatic [31:0] crc_byte(input [31:0] previous,input [7:0] value);
        reg [31:0] c; integer bit_index;
        begin
            c=previous^{24'd0,value};
            for(bit_index=0;bit_index<8;bit_index=bit_index+1)
                c=c[0] ? (c>>1)^32'hedb88320:(c>>1);
            crc_byte=c;
        end
    endfunction
    always @(posedge clk) begin
        read_data<=memory[read_address];
        if(ingress && bridge_addr[11:2]<WORDS)
            memory[bridge_addr[8:2]]<=normalized;
    end
    always @(posedge clk_core) begin
        send_sync<={send_sync[1:0],send_toggle};
        reset_sync<={reset_sync[1:0],reset || receiving};
        clear_sync<={clear_sync[1:0],clear_toggle};
        code[128]<=0;
        if(reset_sync[2] || clear_sync[2]!=clear_ack)begin
            ack_toggle<=send_sync[2];
            clear_ack<=clear_sync[2];
            core_pending<=0;
        end else if(core_pending)begin
            // The consumer samples the preceding cycle's code pulse on this edge.
            // ACK only now, so ready also means the final record was consumed.
            ack_toggle<=pending_toggle;
            core_pending<=0;
        end
        else if(send_sync[2]!=ack_toggle)begin
            code<={1'b1,payload};
            pending_toggle<=send_sync[2];
            core_pending<=1;
        end
    end
    // The toggle also catches a one-bridge-cycle reset shorter than a core clock.
    assign code_reset=reset_sync[2] || clear_sync[2]!=clear_ack;
    always @(posedge clk) begin
        receiving_prev<=receiving;
        reset_prev<=reset;
        // Only one clear may be in flight. A second reset/start coalesces into
        // that clear; two toggles between destination clocks must not cancel.
        if(((reset && !reset_prev) || (receiving && !receiving_prev)) && clear_ack_sync[2]==clear_toggle)
            clear_toggle<=~clear_toggle;
        ack_sync<={ack_sync[1:0],ack_toggle};
        clear_ack_sync<={clear_ack_sync[1:0],clear_ack};
        core_clear_sync<={core_clear_sync[1:0],code_reset};
        if(reset || (receiving && !receiving_prev))begin
            ready<=0;fault<=0;received<=0;count<=0;phase<=IDLE;
            playback<=0;read_address<=0;record_word<=0;crc<=32'hffffffff;
            if(!reset && ingress)begin
                received<=1;
                if(bridge_addr!=BASE || normalized!=32'h48434c50)fault<=1;
            end
        end else begin
            if(ingress)begin
                if(bridge_addr[1:0]!=0 || bridge_addr[11:2]!=received || received>=WORDS || phase!=IDLE)
                    fault<=1;
                else begin
                    received<=received+1'b1;
                    case(received)
                        0:if(normalized!=32'h48434c50)fault<=1;
                        1:if(normalized!={16'd1,PLATFORM})fault<=1;
                        2:begin count<=normalized[5:0];if(normalized<1 || normalized>MAX_CODES)fault<=1;end
                        3:expected_crc<=normalized;
                    endcase
                end
            end
            if(!receiving && receiving_prev)begin
                if(fault || received!=total_words || count==0)fault<=1;
                else begin read_address<=4;crc<=32'hffffffff;phase<=WAIT_RAM;end
            end
            case(phase)
                WAIT_RAM:phase<=CAPTURE;
                CAPTURE:begin
                    word_data<=read_data;byte_index<=0;
                    if(playback)begin
                        case(record_word)
                            0:payload[127:96]<=read_data;
                            1:payload[95:64]<=read_data;
                            2:payload[63:32]<=read_data;
                            3:payload[31:0]<=read_data;
                        endcase
                        record_word<=record_word+1'b1;
                        if(record_word==3)begin send_toggle<=~send_toggle;phase<=DISPATCH_WAIT;end
                        else begin read_address<=read_address+1'b1;phase<=WAIT_RAM;end
                    end else begin
                        if(read_address>=12)begin
                            case(read_address[1:0])
                                0:begin record_flags<=read_data;if(read_data>1)fault<=1;end
                                1:begin
                                    record_address<=read_data;
                                    if((read_data & ~address_mask)!=0 || read_data<MIN_ADDRESS || read_data>MAX_ADDRESS)fault<=1;
                                    if(PLATFORM==5 && read_data[0])fault<=1;
                                    if(PLATFORM==6 && (!read_data[15] || read_data[23:16]==8'h7e || read_data[23:16]==8'h7f))fault<=1;
                                end
                                2:begin record_compare<=read_data;if((read_data & ~data_mask)!=0)fault<=1;end
                                3:if((read_data & ~data_mask)!=0)fault<=1;
                            endcase
                        end
                        phase<=CHECK_CRC;
                    end
                end
                CHECK_CRC:begin
                    crc<=crc_byte(crc,word_data[7:0]);
                    word_data<=word_data>>8;
                    byte_index<=byte_index+1'b1;
                    if(byte_index==3)begin
                        if(read_address+1==total_words)begin
                            if(fault || (crc_byte(crc,word_data[7:0])^32'hffffffff)!=expected_crc)begin fault<=1;phase<=IDLE;end
                            else begin playback<=1;read_address<=12;record_word<=0;phase<=WAIT_CLEAR;end
                        end else begin read_address<=read_address+1'b1;phase<=WAIT_RAM;end
                    end
                end
                DISPATCH_WAIT:if(ack_sync[2]==send_toggle)begin
                    if(read_address+1==total_words)begin ready<=1;phase<=IDLE;end
                    else begin read_address<=read_address+1'b1;phase<=WAIT_RAM;end
                end
                WAIT_CLEAR:if(clear_ack_sync[2]==clear_toggle && !core_clear_sync[2] && ack_sync[2]==send_toggle)
                    phase<=WAIT_RAM;
            endcase
        end
    end
endmodule
