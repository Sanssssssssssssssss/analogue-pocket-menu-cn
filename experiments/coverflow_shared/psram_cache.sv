// SPDX-License-Identifier: MIT
// Cover-only cache on an otherwise unused CellRAM die. Native game/save/SS
// memory never shares this bus. Requests retain ownership until a response.
module coverflow_psram_cache (
    input wire clk,enable,invalidate,begin_upload,
    input wire [6:0] upload_slot,
    input wire write_en,
    input wire [27:0] write_addr,
    input wire [15:0] write_data,
    output wire upload_ready,idle,
    input wire request,
    input wire [23:0] word_address,
    output reg done=0,
    output reg [31:0] data=0,
    output reg fault=0,
    output wire [21:16] cram_a,
    inout wire [15:0] cram_dq,
    input wire cram_wait,
    output wire cram_clk,cram_adv_n,cram_cre,cram_ce0_n,cram_ce1_n,
    output wire cram_oe_n,cram_we_n,cram_ub_n,cram_lb_n
);
    localparam FREE=0,WRITE_WAIT=1,READ_WAIT=2;
    reg [1:0] state=FREE;
    reg [21:0] queued_address[0:7];
    reg [15:0] queued_data[0:7];
    reg [2:0] head=0,tail=0;
    reg [3:0] used=0;
    reg uploading=0;
    reg [6:0] receiving_slot=0;
    reg [14:0] received=0;
    reg read_pending=0;
    reg [21:0] read_address=0;
    wire image_write=write_en && write_addr[27:23]==5'h04;
    wire valid_write=image_write && !write_addr[0] && write_addr[15:0]<45568;
    wire push=image_write && valid_write && enable && uploading && !fault && !invalidate;
    wire pop=state==FREE && !ps_busy && used!=0 && !fault && !invalidate;
    reg ps_write=0,ps_read=0;
    reg [21:0] ps_address=0;
    reg [15:0] ps_input=0;
    wire ps_busy,ps_available;
    wire [15:0] ps_output;
    wire bus_draining=ps_write || ps_read;
    assign idle=state==FREE && !read_pending && used==0 && !ps_busy && !bus_draining;
    assign upload_ready=received==22784 && !uploading && idle && !fault;
    coverflow_psram #(.CLOCK_SPEED(74.25)) memory(.clk(clk),.bank_sel(1'b0),.addr(ps_address),
        .write_en(ps_write),.data_in(ps_input),.write_high_byte(1'b1),.write_low_byte(1'b1),
        .read_en(ps_read),.read_avail(ps_available),.data_out(ps_output),.busy(ps_busy),
        .cram_a(cram_a),.cram_dq(cram_dq),.cram_wait(cram_wait),.cram_clk(cram_clk),
        .cram_adv_n(cram_adv_n),.cram_cre(cram_cre),.cram_ce0_n(cram_ce0_n),.cram_ce1_n(cram_ce1_n),
        .cram_oe_n(cram_oe_n),.cram_we_n(cram_we_n),.cram_ub_n(cram_ub_n),.cram_lb_n(cram_lb_n));
    reg busy_seen=0;
    always @(posedge clk)begin
        ps_write<=0;ps_read<=0;done<=0;
        if(request)begin
            if(read_pending)fault<=1;
            else begin read_pending<=1;read_address<=word_address[21:0];if(word_address[23:22]!=0)fault<=1;end
        end
        if(push)begin
            if(used==8 && !pop)fault<=1;
            else begin queued_address[tail]<=write_addr[22:1];queued_data[tail]<=write_data;tail<=tail+1'b1;end
            if(write_addr[22:16]!=receiving_slot || write_addr[15:1]!=received)fault<=1;
            else if(received==22783)begin received<=22784;uploading<=0;end
            else received<=received+1'b1;
        end else if(image_write && enable && !invalidate)fault<=1;
        case({push && (used<8 || pop),pop})
            2'b10:used<=used+1'b1;2'b01:used<=used-1'b1;default:begin end
        endcase
        case(state)
            FREE:if(pop)begin
                ps_address<=queued_address[head];ps_input<=queued_data[head];head<=head+1'b1;
                ps_write<=1;busy_seen<=0;state<=WRITE_WAIT;
            end else if(read_pending && !ps_busy)begin
                if(fault)begin done<=1;data<=0;read_pending<=0;end
                else begin ps_address<=read_address;ps_read<=1;state<=READ_WAIT;end
            end
            WRITE_WAIT:begin
                if(ps_busy)busy_seen<=1;
                if(busy_seen && !ps_busy)state<=FREE;
            end
            READ_WAIT:if(ps_available)begin
                // The 16-bit fetch adapter deliberately disables DWORD reuse.
                data<={ps_output,ps_output};done<=1;read_pending<=0;state<=FREE;
            end
            default:state<=FREE;
        endcase
        if(begin_upload)begin
            if(used!=0 || uploading)fault<=1;
            receiving_slot<=upload_slot;received<=0;uploading<=1;
        end
        if(invalidate || !enable)begin
            // Discard queued writes, but finish any operation already on pins.
            head<=tail;used<=0;uploading<=0;received<=0;
            if(idle || (!read_pending && state==FREE && !ps_busy))fault<=0;
        end
    end
endmodule
