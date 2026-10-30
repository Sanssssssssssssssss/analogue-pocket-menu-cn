`timescale 1ns/1ps
module tb_launch_guard;
    reg clk=0; always #5 clk=~clk;
    reg reset=1,start=0,params=0,safe=0,ack=0,done=0;
    reg [1:0] platform=0;
    reg [31:0] bytes=32768;
    reg [2:0] err=0;
    wire busy,open_req,read_req,verified;
    wire [3:0] error;
    wire [15:0] slot;
    wire [31:0] address,length;
    integer opens=0,reads=0,successes=0,cases=0;
    launch_guard #(.TIMEOUT(40)) dut(clk,reset,start,platform,bytes,params,safe,
        busy,open_req,read_req,verified,error,slot,address,length,ack,done,err);
    always @(posedge clk) begin
        #1;
        if(open_req)opens=opens+1;
        if(read_req)reads=reads+1;
        if(verified)successes=successes+1;
    end
    task tick(input integer n);repeat(n)begin @(posedge clk);#2;end endtask
    task clean;
        @(negedge clk);reset=1;start=0;params=0;safe=0;ack=0;done=0;err=0;
        bytes=32768;platform=0;tick(2);@(negedge clk);reset=0;tick(1);
        opens=0;reads=0;successes=0;
    endtask
    task begin_load(input [1:0] p);
        @(negedge clk);platform=p;start=1;tick(1);
        @(negedge clk);start=0;tick(1);
    endtask
    task finish_command(input [2:0] failure);
        @(negedge clk);ack=1;done=0;tick(2);
        @(negedge clk);ack=0;err=failure;done=1;tick(2);
        @(negedge clk);done=0;tick(1);
    endtask
    integer p;
    initial begin
        for(p=0;p<2;p=p+1)begin
            clean(); begin_load(2'(p)); tick(5);
            if(opens||reads)$fatal(1,"request before save barrier");
            @(negedge clk);params=1;safe=1;
            wait(open_req);tick(1);
            // Inputs changing while pending must not retarget a load.
            @(negedge clk);platform=2;bytes=1;
            finish_command(0); wait(read_req || reads==1);tick(1);
            if(slot!=(p==0?1:0)||address!=32'h10000000||length!=32768)
                $fatal(1,"descriptor changed while pending");
            finish_command(0);
            if(successes!=1||busy||error)$fatal(1,"normal load failed");
            cases=cases+1;
        end
        clean();params=1;safe=1;begin_load(2);tick(4);
        if(error!=3||opens||reads||successes)$fatal(1,"SNES host loader bypassed");cases=cases+1;
        clean();begin_load(3);tick(4);
        if(error!=2||opens)$fatal(1,"invalid platform accepted");cases=cases+1;
        clean();bytes=0;begin_load(0);tick(4);
        if(error!=2||opens)$fatal(1,"zero size accepted");cases=cases+1;
        clean();bytes=32'h02000001;begin_load(0);tick(4);
        if(error!=2||opens)$fatal(1,"oversize accepted");cases=cases+1;
        clean();begin_load(0);tick(45);
        if(error!=4||opens||successes)$fatal(1,"barrier timeout failed");cases=cases+1;
        clean();params=1;safe=1;begin_load(0);wait(opens==1);finish_command(2);
        if(error!=1||reads||successes)$fatal(1,"open error continued");cases=cases+1;
        clean();params=1;safe=1;begin_load(0);wait(opens==1);finish_command(0);
        wait(reads==1);finish_command(5);
        if(error!=1||successes)$fatal(1,"read error continued");cases=cases+1;
        clean();params=1;safe=1;begin_load(0);wait(opens==1);tick(45);
        if(error!=4||reads||successes)$fatal(1,"ack timeout failed");cases=cases+1;
        clean();params=1;safe=1;done=1;begin_load(0);wait(opens==1);
        @(negedge clk);ack=1;tick(5);@(negedge clk);ack=0;tick(45);
        if(error!=4||reads||successes)$fatal(1,"stale completion was accepted");cases=cases+1;
        $display("PASS: %0d launch guard cases; GBA/NES slots, immutable descriptor, save barrier, SNES refusal, errors and stale-done timeout",cases);
        $finish;
    end
    initial begin #200000; $fatal(1,"watchdog"); end
endmodule
