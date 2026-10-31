// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_fade_video;
    reg clk_sys=0,clk_vid=0;
    always #5 clk_sys=~clk_sys;
    always #59.605 clk_vid=~clk_vid;
    reg reset=1,menu_show=0,menu_active=0;
    wire menu_visible;wire [23:0] video_rgb;
    wire video_de,video_vs,video_hs,video_skip;
    video_adapter display(.clk_sys(clk_sys),.clk_vid(clk_vid),.reset(reset),
        .menu_show(menu_show),.menu_fault(1'b0),.menu_active(menu_active),.menu_visible(menu_visible),
        .pixel_addr(16'd0),.pixel_data(18'd0),.pixel_we(1'b0),
        .video_rgb(video_rgb),.video_de(video_de),.video_vs(video_vs),.video_hs(video_hs),.video_skip(video_skip));
    function [17:0] pattern(input integer n);pattern=(n*37)^18'h2ac3d;endfunction
    function [23:0] expand(input [17:0] p);
        expand={p[17:12],p[17:16],p[11:6],p[11:10],p[5:0],p[5:4]};
    endfunction
    integer n,count;
    initial begin
        for(n=0;n<38400;n=n+1)display.framebuffer[n]=pattern(n);
        repeat(8)@(negedge clk_vid);reset=0;menu_show=1;
        wait(menu_visible && !display.active_frame);@(posedge video_vs);@(negedge video_vs);
        count=0;
        while(count<38400)begin
            @(negedge clk_vid);
            if(video_de && !video_skip)begin
                if(video_rgb!==expand(pattern(count)))$fatal(1,"Game raster altered at %0d",count);
                count=count+1;
            end
        end
        menu_active=1;menu_show=0;
        wait(display.active_frame && !menu_visible);
        if(display.menu_level!==0)$fatal(1,"Menu re-entry not black");
        $display("PASS: actual video adapter preserves all 38400 game raster pixels and enters menu black");$finish;
    end
    initial begin #100000000;$fatal(1,"game bypass watchdog");end
endmodule
