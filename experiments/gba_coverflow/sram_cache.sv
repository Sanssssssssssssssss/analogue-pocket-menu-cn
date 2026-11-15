// SPDX-License-Identifier: MIT
// Five RGB565 atlases in the otherwise unused 128K x 16 asynchronous SRAM.
// Each slot occupies 22,784 words; 113,920 of 131,072 words are used.
// 100.663296 MHz only: 8-cycle accesses, 3-cycle bus turnaround.
module coverflow_sram_cache (
    input wire clk,enable,invalidate,begin_upload,
    input wire [2:0] upload_slot,
    input wire write_en,
    input wire [27:0] write_addr,
    input wire [15:0] write_data,
    output wire upload_ready,idle,
    input wire request,
    input wire [23:0] word_address,
    output reg done=0,
    output reg [31:0] data=0,
    output reg fault=0,
    (* preserve, dont_merge *) output reg [16:0] sram_a=0,
    inout wire [15:0] sram_dq,
    (* preserve, dont_merge *) output reg sram_oe_n=1,sram_we_n=1,sram_ub_n=1,sram_lb_n=1
);
    localparam FREE=0,WRITE_SETUP=1,WRITE_ACTIVE=2,WRITE_HOLD=3,
               READ_LOW=4,READ_HIGH=5,READ_RELEASE=6;
    reg [2:0] state=FREE;
    reg [3:0] timer=0;
    (* preserve, dont_merge *) reg drive=0;
    (* preserve, dont_merge *) reg [15:0] pin_output=0,pin_input=0;
    reg [15:0] read_low=0;
    assign sram_dq=drive ? pin_output:16'hzzzz;
    // One physical input register can be packed into the I/O element.
    always @(posedge clk)pin_input<=sram_dq;

    function automatic [16:0] packed_word(input [2:0] slot,input [14:0] offset);
        reg [16:0] base;
        begin
            case(slot)
                0:base=17'h00000;1:base=17'h05900;2:base=17'h0B200;
                3:base=17'h10B00;4:base=17'h16400;default:base=0;
            endcase
            packed_word=base+{2'b0,offset};
        end
    endfunction
    (* ramstyle="M10K" *) reg [32:0] queued_words[0:7];
    reg [32:0] queue_q;
    reg queue_ready=0;
    reg [2:0] head=0,tail=0,receiving_slot=0;
    reg [3:0] used=0;
    always @(posedge clk)queue_q<=queued_words[head];
    reg [14:0] received=0;
    reg receiving=0,complete=0,read_pending=0;
    reg [16:0] read_address=0;
    wire image_write=write_en && write_addr[27:19]==9'h040;
    wire valid_write=write_addr[18:16]<5 && !write_addr[0] && write_addr[15:0]<45568;
    wire valid_read=word_address[23:18]==0 && word_address[17:15]<5 && word_address[14:0]<22784;
    wire push=image_write && valid_write && enable && receiving && !fault && !invalidate;
    wire pop=state==FREE && used!=0 && queue_ready && !fault && !invalidate;
    assign idle=state==FREE && used==0 && !read_pending && !request;
    // Completion persists during raster reads, so CDC cannot miss an idle pulse.
    assign upload_ready=complete && !fault;

    always @(posedge clk)begin
        done<=0;queue_ready<=used!=0 && !pop;
        if(request)begin
            if(read_pending || !valid_read)fault<=1;
            if(!read_pending)begin
                read_pending<=1;
                read_address<=packed_word(word_address[17:15],{word_address[14:1],1'b0});
            end
        end
        if(push)begin
            if(used==8 && !pop)fault<=1;
            else begin
                queued_words[tail]<={packed_word(write_addr[18:16],write_addr[15:1]),write_data};
                tail<=tail+1'b1;
            end
            if(write_addr[18:16]!=receiving_slot || write_addr[15:1]!=received)fault<=1;
            else if(received==22783)begin received<=22784;receiving<=0;end
            else received<=received+1'b1;
        end else if(image_write && enable && !invalidate)fault<=1;
        case({push && (used<8 || pop),pop})
            2'b10:used<=used+1'b1;2'b01:used<=used-1'b1;default:begin end
        endcase
        if(received==22784 && !receiving && used==0 && !push &&
           state!=WRITE_SETUP && state!=WRITE_ACTIVE && state!=WRITE_HOLD)complete<=1;
        case(state)
            FREE:if(pop)begin
                sram_a<=queue_q[32:16];pin_output<=queue_q[15:0];head<=head+1'b1;
                drive<=1;sram_oe_n<=1;sram_we_n<=1;sram_lb_n<=0;sram_ub_n<=0;
                state<=WRITE_SETUP;
            end else if(read_pending)begin
                if(fault)begin data<=0;done<=1;read_pending<=0;end
                else begin
                    sram_a<=read_address;drive<=0;sram_oe_n<=0;sram_we_n<=1;
                    sram_lb_n<=0;sram_ub_n<=0;timer<=8;state<=READ_LOW;
                end
            end
            WRITE_SETUP:begin sram_we_n<=0;timer<=8;state<=WRITE_ACTIVE;end
            WRITE_ACTIVE:if(timer==1)begin sram_we_n<=1;timer<=3;state<=WRITE_HOLD;end
                else timer<=timer-1'b1;
            WRITE_HOLD:if(timer==1)begin
                    drive<=0;sram_lb_n<=1;sram_ub_n<=1;state<=FREE;
                end else timer<=timer-1'b1;
            READ_LOW:if(timer==1)begin
                    read_low<=pin_input;sram_a<=read_address+1'b1;timer<=8;state<=READ_HIGH;
                end else timer<=timer-1'b1;
            READ_HIGH:if(timer==1)begin
                    data<={pin_input,read_low};sram_oe_n<=1;sram_lb_n<=1;sram_ub_n<=1;
                    timer<=3;state<=READ_RELEASE;
                end else timer<=timer-1'b1;
            READ_RELEASE:if(timer==1)begin done<=1;read_pending<=0;state<=FREE;end
                else timer<=timer-1'b1;
            default:state<=FREE;
        endcase
        if(begin_upload)begin
            if(used!=0 || receiving || upload_slot>=5)fault<=1;
            received<=0;receiving_slot<=upload_slot;receiving<=1;complete<=0;
        end
        if(invalidate || !enable)begin
            // Pin operations and pending responses finish before ownership ends.
            head<=tail;used<=0;receiving<=0;received<=0;complete<=0;queue_ready<=0;
            if(state==FREE && !read_pending)fault<=0;
        end
    end
endmodule
