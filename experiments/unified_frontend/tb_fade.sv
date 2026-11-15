// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_fade;
    reg clk=0;always #5 clk=~clk;
    reg reset=1,frame_tick=0,enabled=1,requested_visible=0;
    reg [23:0] pixel=24'hffffff;
    wire [3:0] level;wire blank;wire [23:0] gained_pixel;
    menu_fade dut(.*);
    integer n,k,expected;
    task frame;
        begin
            @(negedge clk);frame_tick=1;@(negedge clk);frame_tick=0;
        end
    endtask
    task pixels;
        input integer gain;
        integer value,r,g,b;
        begin
            for(value=0;value<256;value=value+1)begin
                r=value;g=255-value;b=value^85;
                pixel={r[7:0],g[7:0],b[7:0]};#1;
                r=(r*gain)>>3;g=(g*gain)>>3;b=(b*gain)>>3;
                if(gained_pixel!=={r[7:0],g[7:0],b[7:0]})$fatal(1,"Pixel gain mismatch");
            end
        end
    endtask
    initial begin
        repeat(2)@(negedge clk);reset=0;#1;
        if(level!==0 || !blank)$fatal(1,"Boot must be black");
        pixels(0);requested_visible=1;
        repeat(4)@(negedge clk);
        if(level!==0)$fatal(1,"Gain changed outside frame tick");
        for(n=1;n<=8;n=n+1)begin
            frame();if(level!==n || blank)$fatal(1,"Fade-in sequence");
            pixels(n);$display("GAIN,in,%0d",level);
        end
        frame();if(level!==8)$fatal(1,"Gain exceeded unity");
        requested_visible=0;
        for(n=6;n>=0;n=n-2)begin
            frame();if(level!==n || blank!==(n==0))$fatal(1,"Fade-out sequence");
            pixels(n);$display("GAIN,out,%0d",level);
        end
        repeat(3)frame();if(!blank)$fatal(1,"Upload wait must remain black");
        enabled=0;pixels(8);
        if(blank)$fatal(1,"Game bypass must not be blanked");
        repeat(2)@(negedge clk);enabled=1;#1;
        if(level!==0 || !blank)$fatal(1,"Menu re-entry must start black");
        requested_visible=1;frame();frame();reset=1;
        @(negedge clk);#1;if(level!==0)$fatal(1,"Reset during fade");
        $display("PASS: vblank gain, 9x256 channel patterns, upload wait, game bypass and reset");
        $finish;
    end
endmodule
