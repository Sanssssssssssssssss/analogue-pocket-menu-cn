`timescale 1ns/1ps
module tb_memory_bridge;
    reg sc=0,mc=0;always #7 sc=~sc;always #5 mc=~mc;
    reg request=0;
    reg [23:0] address=0;
    wire done,idle,fault,mrequest;
    wire [31:0] data;
    wire [23:0] maddress;
    reg mdone=0;reg [31:0] mdata=0;
    reg busy=0,spurious=0;
    reg [23:0] saved=0;
    integer delay_count=0,issued=0,received=0,n;
    function [31:0] result(input [23:0] a);result={a,8'hA7}^32'hDE3A519C;endfunction
    coverflow_memory_bridge dut(.source_clock(sc),.memory_clock(mc),.source_request(request),.source_word_address(address),
        .source_done(done),.source_data(data),.source_idle(idle),.source_fault(fault),.memory_request(mrequest),
        .memory_word_address(maddress),.memory_done(mdone),.memory_data(mdata));
    always @(posedge mc)begin
        mdone<=0;
        if(spurious && !busy)begin mdone<=1;mdata<=32'hbad0bad0;end
        if(mrequest)begin
            if(busy)$fatal(1,"overlapping native reads");
            busy<=1;saved<=maddress;delay_count<=issued%16;issued<=issued+1;
        end else if(busy)begin
            if(delay_count==0)begin mdata<=result(saved);mdone<=1;busy<=0;end
            else delay_count<=delay_count-1;
        end
    end
    always @(negedge sc)if(done)received=received+1;
    task read(input [23:0] value,input integer duplicate);
        begin
            @(negedge sc);address=value;request=1;@(negedge sc);request=0;
            if(idle)$fatal(1,"read ownership lost before response");
            if(duplicate)begin @(negedge sc);request=1;address=24'hbadbad;@(negedge sc);request=0;end
            wait(done);@(negedge sc);
            if(data!==result(value))$fatal(1,"response crossed into the wrong read");
            repeat(3)@(negedge sc);
            if(!idle)$fatal(1,"completed read ownership retained");
        end
    endtask
    initial begin
        spurious=1;repeat(4)@(negedge mc);spurious=0;repeat(8)@(negedge sc);
        if(done || fault)$fatal(1,"unowned completion accepted");
        for(n=0;n<64;n=n+1)begin read((n*77113)&24'h3fffff,0);if(fault)$fatal(1,"legal transfer fault");end
        read(24'h023456,1);
        if(!fault || issued!=65 || received!=65)$fatal(1,"duplicate read lost/replaced an outstanding transaction %d/%d",issued,received);
        $display("PASS: 65 asynchronous memory reads, variable response latency, stable address/data, ownership until response, idle completions ignored and duplicate request rejected");$finish;
    end
    initial begin #1000000;$fatal(1,"memory bridge watchdog");end
endmodule
