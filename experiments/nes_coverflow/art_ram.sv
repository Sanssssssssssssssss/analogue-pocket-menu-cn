// SPDX-License-Identifier: MIT
// Five packed 45,568-byte cover/mip images. This RAM is independent of the
// native NES ROM/save SDRAM. A slot is published only after a contiguous upload.
module nes_coverflow_art_ram (
    input wire clk,enable,invalidate,begin_upload,
    input wire [2:0] upload_slot,
    input wire write_en,
    input wire [27:0] write_addr,
    input wire [15:0] write_data,
    output wire upload_ready,
    input wire request,
    input wire [23:0] word_address,
    output reg done=0,
    output reg [31:0] data=0,
    output reg fault=0
);
    localparam WORDS_PER_SLOT=22784,DWORDS_PER_SLOT=11392,DEPTH=56960;
    (* ramstyle="M10K,no_rw_check" *) reg [15:0] even_words[0:DEPTH-1];
    (* ramstyle="M10K,no_rw_check" *) reg [15:0] odd_words[0:DEPTH-1];
    reg [14:0] received=0;
    reg [2:0] receiving_slot=0;
    reg receiving=0,complete=0;
    wire image_write=write_en && write_addr[27:19]==9'h040;
    wire valid_write=image_write && write_addr[18:16]<5 && write_addr[15:0]<45568 && !write_addr[0];
    wire [15:0] write_index=write_addr[18:16]*16'd11392+{2'd0,write_addr[15:2]};
    wire [15:0] read_index=word_address[17:15]*16'd11392+{2'd0,word_address[14:1]};
    wire valid_read=word_address[23:18]==0 && word_address[17:15]<5 && word_address[14:0]<WORDS_PER_SLOT;
    reg [15:0] read_address=0;
    reg read_valid=0,read_valid_1=0;
    reg [15:0] even_q=0,odd_q=0;
    assign upload_ready=complete && !fault;
    always @(posedge clk)begin
        done<=read_valid_1;read_valid_1<=read_valid;read_valid<=request;
        if(request)begin read_address<=valid_read ? read_index:16'd0;if(!valid_read)fault<=1;end
        even_q<=even_words[read_address];odd_q<=odd_words[read_address];
        if(read_valid_1)data<={odd_q,even_q};
        if(valid_write && enable && receiving && !fault)begin
            if(write_addr[1])odd_words[write_index]<=write_data;
            else even_words[write_index]<=write_data;
            if(write_addr[18:16]!=receiving_slot || write_addr[15:1]!=received)fault<=1;
            else if(received==WORDS_PER_SLOT-1)begin complete<=1;receiving<=0;end
            else received<=received+1'b1;
        end else if(image_write && (!valid_write || !enable || !receiving))fault<=1;
        if(begin_upload)begin
            received<=0;receiving_slot<=upload_slot;receiving<=1;complete<=0;
            if(upload_slot>=5)fault<=1;
        end
        if(invalidate || !enable)begin receiving<=0;complete<=0;fault<=0;end
    end
endmodule
