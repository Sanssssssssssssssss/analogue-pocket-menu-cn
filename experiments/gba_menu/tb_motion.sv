`timescale 1ns/1ps
module tb_motion;
    reg sys=0,vid=0,sys_run=0;
    always begin wait(sys_run);#5;sys=~sys;end
    always #60 vid=~vid;
    reg reset=1,show=0,owned=1,motion=1,forward=1,fault=0;
    reg [15:0] addr=0;reg [17:0] data=0;reg we=0;
    wire [23:0] rgb;wire de,vs,hs,skip,visible;
    video_adapter dut(.clk_sys(sys),.clk_vid(vid),.reset(reset),
        .menu_show(show),.menu_fault(fault),.menu_active(owned),.menu_motion(motion),.menu_forward(forward),.menu_visible(visible),
        .pixel_addr(addr),.pixel_data(data),.pixel_we(we),.video_rgb(rgb),.video_de(de),.video_vs(vs),.video_hs(hs),.video_skip(skip));
    reg real_pages=0;
    reg [17:0] page1[0:38399],page2[0:38399],page3[0:38399];
    initial if($test$plusargs("real_pages"))begin
        real_pages=1;$readmemh("page1.hex",page1);$readmemh("page2.hex",page2);$readmemh("page3.hex",page3);
    end
    function [17:0] pattern(input integer page,x,y);
        reg [4:0] r,b;reg [5:0] g;
        begin
            r=(x+page*7)%32;g=(y+page*11)%64;b=(x+y+page*3)%32;
            if(real_pages)case(page)1:pattern=page1[y*240+x];2:pattern=page2[y*240+x];default:pattern=page3[y*240+x];endcase
            else if(dut.cover_at(x,y))pattern={r,r[4],g,b,b[4]};
            else if(y>=108 && y<141 && x>=11 && x<224 && ((x+y)%5)<2)pattern=18'h3be77;
            else pattern=0;
        end
    endfunction
    function [23:0] expand(input [17:0] p);
        expand={p[17:12],p[17:16],p[11:6],p[11:10],p[5:0],p[5:4]};
    endfunction
    task upload(input integer page);
        integer n;begin sys_run=1;
            for(n=0;n<38400;n=n+1)begin @(negedge sys);we=1;addr=n;data=pattern(page,n%240,n/240);end
            @(negedge sys);we=0;sys_run=0;
        end
    endtask
    integer checks=0,frames=0;
    task check_frame(input integer old_page,new_page,delta,input integer dir,input integer dump_id);
        integer n,x,y,source_x,source_page,file;reg [23:0] expected;
        begin
            if(!vs)@(posedge vs);@(negedge vs);n=0;file=0;
            if(dump_id>=0)begin file=$fopen($sformatf("frame-%0d.ppm",dump_id),"wb");$fwrite(file,"P6\n240 160\n255\n");end
            while(n<38400)begin
                @(negedge vid);
                if(de && !skip)begin
                    x=n%240;y=n/240;
                    if(dir==1)begin source_page=x<240-delta ? old_page:new_page;source_x=x<240-delta ? x+delta:x+delta-240;end
                    else begin source_page=x>=delta ? old_page:new_page;source_x=x>=delta ? x-delta:x+240-delta;end
                    expected=expand(pattern(source_page,source_x,y));
                    if(rgb!==expected)$fatal(1,"frame delta=%0d dir=%0d pixel=%0d got=%h expected=%h",delta,dir,n,rgb,expected);
                    if(file)$fwrite(file,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);n=n+1;checks=checks+1;
                end
            end
            if(file)$fclose(file);frames=frames+1;
        end
    endtask
    integer i;reg [8:0] d;
    initial begin
        repeat(8)@(negedge vid);reset=0;upload(1);show=1;wait(visible);
        check_frame(1,1,0,1,0);
        // Complete old covers/title are retained while the main RAM is replaced.
        show=0;wait(!visible);upload(2);check_frame(1,2,0,1,1);
        show=1;wait(dut.animating);if(visible)$fatal(1,"navigation enabled during transition");
        for(i=0;i<8;i=i+1)begin d=dut.distance(i);check_frame(1,2,d,1,i+2);end
        wait(visible);check_frame(2,2,0,1,10);
        forward=0;show=0;wait(!visible);upload(3);check_frame(2,3,0,0,-1);
        show=1;wait(dut.animating);
        for(i=0;i<8;i=i+1)begin d=dut.distance(i);check_frame(2,3,d,0,-1);end
        wait(visible);check_frame(3,3,0,1,-1);
        // Leaving the menu clears cached ownership. All 18 game bits pass through
        // unchanged, including colors which cannot occur in RGB565 menu assets.
        owned=0;motion=0;show=0;wait(!visible);
        sys_run=1;for(i=0;i<38400;i=i+1)begin @(negedge sys);we=1;addr=i;data=(i*37+19)&18'h3ffff;end
        @(negedge sys);we=0;sys_run=0;show=1;wait(visible);@(posedge vs);@(negedge vs);i=0;
        while(i<38400)begin @(negedge vid);if(de&&!skip)begin
            if(rgb!==expand((i*37+19)&18'h3ffff))$fatal(1,"game color changed at %0d",i);i=i+1;end end
        // A reset discards an incomplete cached page and keeps output hidden.
        reset=1;repeat(10)@(negedge vid);if(visible)$fatal(1,"reset retained menu visibility");
        $display("PASS: %0d full frames, %0d compared menu pixels; forward/reverse eight-frame easing, upload retention, final colors, 38400 full-depth game pixels, reset",frames,checks);$finish;
    end
    initial begin #1200000000;$fatal(1,"motion watchdog");end
endmodule
