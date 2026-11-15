`timescale 1ns/1ps
module tb_menu;
    reg clk=0; always #5 clk=~clk;
    reg reset=1;
    reg [15:0] buttons=0;
    wire request, ready, launch;
    wire [2:0] page;
    wire [1:0] platform, entry, selected;
    reg we=0, commit=0, failed=0;
    reg [10:0] wa=0;
    reg [15:0] wd=0;
    wire [23:0] rgb;
    wire de,hs,vs;
    reg [15:0] pages [0:12287];
    integer launches=0, last_platform=-1, last_entry=-1;
    integer black_pixels=0;
    menu_shell dut(clk,reset,buttons,request,page,we,wa,wd,commit,ready,
                   launch,platform,entry,failed,rgb,de,hs,vs,selected);
    always @(posedge clk) begin
        #1;
        if (launch) begin launches=launches+1; last_platform=platform; last_entry=entry; end
        if (!dut.ready_d && de && !reset) begin
            if (rgb !== 24'h000000) $fatal(1,"nonblack loading pixel");
            black_pixels=black_pixels+1;
        end
    end
    task tick(input integer n); repeat(n) begin @(posedge clk); #2; end endtask
    task press(input integer bit_number);
        @(negedge clk); buttons=16'(1<<bit_number);
        tick(12); @(negedge clk); buttons=0; tick(12);
    endtask
    task load_page;
        integer i, expected_page;
        begin
            expected_page=page;
            for(i=0;i<2048;i=i+1) begin
                @(negedge clk); we=1; wa=11'(i); wd=pages[expected_page*2048+i];
            end
            @(negedge clk); we=0; commit=1;
            @(negedge clk); commit=0;
            wait(ready); tick(3);
            if(page!=expected_page) $fatal(1,"page changed while loading");
        end
    endtask
    task capture(input string filename);
        integer file_handle, pixels, lit;
        begin
            @(posedge vs); @(negedge vs);
            file_handle=$fopen(filename,"wb");
            $fwrite(file_handle,"P6\n320 240\n255\n");
            pixels=0; lit=0;
            while(pixels<76800) begin
                @(posedge clk); #2;
                if(de) begin
                    $fwrite(file_handle,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);
                    pixels=pixels+1;
                    if(rgb!=0)lit=lit+1;
                end
            end
            $fclose(file_handle);
            if(lit<1000)$fatal(1,"blank text page");
        end
    endtask
    integer p,i;
    initial begin
        $readmemh("pages.hex",pages);
        tick(4); @(negedge clk); reset=0; tick(2);
        // Incomplete cache must never be presented, even at a frame boundary.
        @(negedge clk); commit=1; tick(2); @(negedge clk); commit=0;
        tick(105000); if(ready)$fatal(1,"incomplete page accepted");
        load_page(); capture("home.ppm");
        press(5); load_page(); if(page!=0)$fatal(1,"B at root changed root");
        press(0); if(selected!=2)$fatal(1,"up wrap failed");
        press(1); if(selected!=0)$fatal(1,"down wrap failed");
        for(p=0;p<3;p=p+1) begin
            for(i=0;i<p;i=i+1)press(1);
            press(4); if(page!=p+1)$fatal(1,"wrong platform page");
            load_page();
            if(p==0)capture("gba.ppm");
            if(p==1)capture("nes.ppm");
            if(p==2)capture("snes.ppm");
            press(1); press(1); press(4);
            if(last_platform!=p || last_entry!=2 || launches!=p+1)
                $fatal(1,"wrong launch descriptor or duplicate launch");
            if(page!=4)$fatal(1,"loading page missing");
            load_page();
            @(negedge clk); failed=1; tick(1); @(negedge clk); failed=0;
            if(page!=5)$fatal(1,"error page missing");
            load_page(); press(5); load_page();
            if(page!=0)$fatal(1,"B failed to recover");
        end
        if(black_pixels<76800)$fatal(1,"loading blanking was not exercised");
        $display("PASS: native GBA/NES/SNES pages, selection, parent B, error return, 3 exact launch intents; %0d black loading pixels",black_pixels);
        $finish;
    end
    initial begin #100000000; $fatal(1,"watchdog"); end
endmodule
