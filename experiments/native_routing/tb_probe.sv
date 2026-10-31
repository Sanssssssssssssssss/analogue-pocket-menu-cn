// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_probe;
    reg clk=0;always #5 clk=~clk;
    reg reset=1,run_reset_n=0,write=0;
    reg [15:0] keys=0;reg [7:0] address=0;reg [31:0] value=0;
    wire [31:0] a,b;
    route_probe #(.CYCLES_PER_MS(2)) pa(clk,reset,run_reset_n,keys,address,write,value,a);
    route_probe #(.ID(32'h504C4201),.CYCLES_PER_MS(2)) pb(clk,reset,run_reset_n,keys,address,write,value,b);
    task tick;begin repeat(5)@(negedge clk);end endtask
    task put(input [7:0] addr,input [31:0] data);
        begin address=addr;value=data;write=1;@(negedge clk);write=0;tick;end
    endtask
    initial begin
        tick;reset=0;tick;
        address=0;#1;if(a!==32'h504C4100 || b!==32'h504C4201)$fatal(1,"identity");
        put(0,32'hDEADBEEF);if(a!==32'h504C4100 || b!==32'h504C4201)$fatal(1,"identity writable");
        address=8;#1;if(a==0)$fatal(1,"stopped during APF reset");
        keys=16'h10;tick;put(8'h10,1);address=8'h14;#1;if(a!=0)$fatal(1,"held key accepted");
        keys=0;tick;keys=16'h30;tick;if(a!=0)$fatal(1,"two buttons accepted");
        keys=0;tick;keys=16'h10;tick;if(a!=1 || b!=1)$fatal(1,"fresh A missing");
        keys=16'h20;tick;if(a!=1)$fatal(1,"choice not latched");
        put(8'h10,2);address=8'h14;#1;if(a!=0)$fatal(1,"phase did not clear");
        keys=0;tick;keys=16'h20;tick;if(a!=2)$fatal(1,"fresh B missing");
        run_reset_n=1;address=4;#1;if(a!=1)$fatal(1,"APF reset status missing");
        keys=0;tick;address=8'h1C;#1;if(a!=32'h20)$fatal(1,"last key lost");
        put(8'h20,32'hE2);if(a!=32'hE2)$fatal(1,"result report missing");
        put(8'h24,32'h504C4201);if(a!=32'h504C4201)$fatal(1,"detail report missing");
        address=0;#1;if(a!==32'h504C4100 || b!==32'h504C4201)$fatal(1,"identity changed");
        $display("PASS: immutable A/B IDs, live clock during APF reset, phase/release/choice and reset status");$finish;
    end
    initial begin #100000;$fatal(1,"watchdog");end
endmodule
