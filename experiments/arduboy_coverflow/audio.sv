// SPDX-License-Identifier: MIT
// Preserve the upstream I2S bit sequence with one 74.25MHz clock. MCLK and
// SCLK edges are enables; no fabric-generated signal clocks a register.
module ard_audio(input wire clk,input wire buzzer1,buzzer2,
    input wire enable1,enable2,limit_volume,mute,
    output reg mclk=0,lrck=0,dac=0);
    // Only the two AVR buzzer signals cross clock domains. Decode their levels
    // after the synchronizers so the 32-bit sample itself is synchronous.
    (* async_reg="true", preserve *) reg [2:0] b1_sync=0,b2_sync=0;
    always @(posedge clk)begin b1_sync<={b1_sync[1:0],buzzer1};b2_sync<={b2_sync[1:0],buzzer2};end
    wire b1=enable1 && b1_sync[2],b2=enable2 && b2_sync[2];
    wire [31:0] positive=limit_volume ? {2'b0,{30{b1}}}:{1'b0,{31{b1}}};
    wire [31:0] negative=b2 ? (limit_volume ? 32'hc0000001:32'h80000001):32'd0;
    wire [31:0] sample=mute || (b1 && b2) ? 32'd0:positive+negative;
    reg [21:0] accumulator=0;
    reg [1:0] divider=0;
    reg [4:0] word_count=0;
    reg [31:0] sample1=0,sample2=0,sample3=0,shift=0;
    always @(posedge clk)begin
        accumulator<=accumulator+22'd245760;
        if(accumulator>=22'd742500)begin
            accumulator<=accumulator-22'd742500+22'd245760;
            mclk<=~mclk;
            if(!mclk)begin
                divider<=divider+1'b1;
                // Original synch_3 sampled on the rising edge of SCLK.
                if(divider==1)begin sample1<=sample;sample2<=sample1;sample3<=sample2;end
                // Original serializer updated on the falling edge of SCLK.
                if(divider==3)begin
                    dac<=shift[31];word_count<=word_count+1'b1;
                    if(word_count==31)begin
                        lrck<=~lrck;
                        if(!lrck)shift<=sample3;
                    end else if(word_count<16)shift<={shift[30:0],1'b0};
                end
            end
        end
    end
endmodule
