`timescale 1ns/1ps
// Compare the complete game raster to the accepted adapter, including blanking,
// sync and scaler skip. No game CPU or physical display is modeled.
module tb_game_video;
    reg memory=0,video=0,write_clock=1;
    always begin wait(write_clock);#5;memory=~memory;end
    always #60 video=~video;
    reg reset=1,show=0,we=0;
    reg [15:0] address=0;reg [17:0] pixel=0;
    wire [23:0] rgb,reference_rgb;
    wire de,vs,hs,skip,visible,reference_de,reference_vs,reference_hs,reference_skip,reference_visible;
    video_adapter candidate(.clk_sys(memory),.clk_vid(video),.reset(reset),.menu_show(show),.menu_fault(1'b0),
        .menu_active(1'b0),.menu_motion(1'b0),.menu_forward(1'b1),.menu_visible(visible),
        .pixel_addr(address),.pixel_data(pixel),.pixel_we(we),.video_rgb(rgb),.video_de(de),.video_vs(vs),.video_hs(hs),.video_skip(skip));
    video_reference reference(.clk_sys(memory),.clk_vid(video),.reset(reset),.menu_show(show),.menu_fault(1'b0),.menu_visible(reference_visible),
        .pixel_addr(address),.pixel_data(pixel),.pixel_we(we),.video_rgb(reference_rgb),.video_de(reference_de),.video_vs(reference_vs),.video_hs(reference_hs),.video_skip(reference_skip));
    integer i,samples=0,active_pixels=0,vs_pulses=0,hs_pulses=0;reg previous_vs=0,previous_hs=0;
    initial begin
        repeat(10)@(negedge video);reset=0;
        for(i=0;i<38400;i=i+1)begin @(negedge memory);address=i;pixel=(i*173+31)&18'h3ffff;we=1;end
        @(negedge memory);we=0;write_clock=0;show=1;wait(visible && reference_visible);
        @(posedge vs);@(negedge vs);
        for(i=0;i<2*308*228*2;i=i+1)begin
            @(negedge video);
            if({rgb,de,vs,hs,skip}!=={reference_rgb,reference_de,reference_vs,reference_hs,reference_skip})
                $fatal(1,"game raster changed at sample %0d candidate=%h/%b%b%b%b reference=%h/%b%b%b%b",i,rgb,de,vs,hs,skip,reference_rgb,reference_de,reference_vs,reference_hs,reference_skip);
            if(de&&!skip)active_pixels=active_pixels+1;
            if(vs&&!previous_vs)vs_pulses=vs_pulses+1;if(hs&&!previous_hs)hs_pulses=hs_pulses+1;
            previous_vs=vs;previous_hs=hs;samples=samples+1;
        end
        if(active_pixels!=76800 || vs_pulses!=2 || hs_pulses!=456)$fatal(1,"wrong complete raster totals %0d %0d %0d",active_pixels,vs_pulses,hs_pulses);
        $display("PASS: %0d clock samples, 76800 game pixels, sync/blanking/scaler-skip bit-identical to accepted adapter across two frames",samples);$finish;
    end
    initial begin #100000000;$fatal(1,"game raster watchdog");end
endmodule
