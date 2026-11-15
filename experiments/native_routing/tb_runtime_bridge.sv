// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_runtime_bridge;
    reg clk=0; always #5 clk=~clk;
    reg ss=0,host=0,sclk=0,mosi=0,miso=0;
    tri old_clk,old_mosi,old_miso,new_clk,new_mosi,new_miso;
    assign old_clk=host?sclk:1'bz;assign new_clk=host?sclk:1'bz;
    assign old_mosi=host?mosi:1'bz;assign new_mosi=host?mosi:1'bz;
    assign old_miso=host?miso:1'bz;assign new_miso=host?miso:1'bz;
    wire [31:0] old_addr,new_addr,raw,buffered,old_wr_data,new_wr_data;
    wire old_rd,new_rd,old_wr,new_wr;
    io_bridge_peripheral old_bridge(clk,1'b1,1'b0,old_addr,,old_rd,raw,old_wr,old_wr_data,old_mosi,old_miso,old_clk,ss);
    io_bridge_peripheral new_bridge(clk,1'b1,1'b0,new_addr,,new_rd,buffered,new_wr,new_wr_data,new_mosi,new_miso,new_clk,ss);
    runtime_request path_source(.clk(clk),.power_reset(1'b0),.run_reset_n(1'b0),.in_menu(1'b0),.buttons(16'd0),
        .address(new_addr),.write_data(32'd0),.write(1'b0),.ack(1'b0),.done(1'b0),.error(3'd0),.read_data(raw));
    runtime_param_buffer buffer(clk,new_rd,new_addr,raw,buffered);
    integer i,j;reg [31:0] bad,good;
    reg [287:0] bad_path=0,good_path=0;
    task tick;begin repeat(16)@(negedge clk);end endtask
    task get(input [31:0] address,output [31:0] a,b);
        begin
            ss=1;host=0;tick;
            host=1;sclk=0;ss=0;tick;
            for(j=15;j>=0;j=j-1)begin
                sclk=0;mosi=address[j*2+1];miso=address[j*2];
                repeat(4)@(negedge clk);sclk=1;repeat(4)@(negedge clk);
            end
            host=0;a=0;b=0;
            wait(new_bridge.spis==2);
            for(j=0;j<16;j=j+1)begin
                @(posedge new_clk);#1;a={a[29:0],old_mosi,old_miso};b={b[29:0],new_mosi,new_miso};
            end
            wait(new_bridge.state==5);ss=1;tick;
        end
    endtask
    initial begin
        tick;ss=1;tick;
        // APF's documented previous-word protocol primes at base, then advances.
        get(32'hF3000000,bad,good);
        for(i=0;i<66;i=i+1)begin
            get(32'hF3000004+i*4,bad,good);
            if(i<9)begin bad_path={bad_path[255:0],bad};good_path={good_path[255:0],good};end
            else if(good!==0)$fatal(1,"nonzero padding/flags/size at word %d",i);
        end
        if(good_path!=={"/Assets/routetest/common/probe.dat",16'd0})$fatal(1,"buffered path %h",good_path);
        if(bad_path[287:256]!=="ets/")$fatal(1,"old offset reproduction %h",bad_path);
        if(old_wr||new_wr)$fatal(1,"unexpected write");
        $display("PASS: actual serial APF bridge; old combinational path begins ets/; buffered path exact, NUL padding/flags/size zero over all 66 words");
        $finish;
    end
    initial begin #5000000;$fatal(1,"serial bridge watchdog: state=%h spis=%h addr=%h rx=%h ss=%b",new_bridge.state,new_bridge.spis,new_addr,new_bridge.rx_byte,new_bridge.phy_spiss_s);end
endmodule
