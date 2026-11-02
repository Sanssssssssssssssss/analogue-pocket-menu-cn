`timescale 1ns/1ps
module tb_assoc_cache;
    reg clk=0;always #5 clk=~clk;
    reg enable=1,invalidate=0,keys_valid=1,commit=0;
    reg [10:0] candidates[0:4],visible[0:3],commit_game=0;
    reg [2:0] commit_slot=0;
    wire want;wire [10:0] wanted_game;wire [2:0] wanted_slot,physical[0:3];wire loaded[0:3];
    coverflow_assoc_cache dut(.*);
    integer counts[0:8];
    integer c,k,d,n,i,j,fills=0,selections=0,attempt;
    function integer wrapped(input integer value,input integer total);
        begin wrapped=((value%total)+total)%total;end
    endfunction
    task fill;
        begin
            attempt=0;#1;
            while(want)begin
                if(attempt>=5 || wanted_slot>=5)$fatal(1,"associative fill did not converge");
                for(j=0;j<4;j=j+1)if(loaded[j] && physical[j]==wanted_slot)$fatal(1,"evicted visible cover");
                commit_slot=wanted_slot;commit_game=wanted_game;
                // No partially uploaded image may appear loaded before commit.
                repeat(3)@(negedge clk);
                commit=1;@(negedge clk);commit=0;#1;
                attempt=attempt+1;fills=fills+1;
            end
            for(j=0;j<4;j=j+1)if(!loaded[j] || dut.tags[physical[j]]!=visible[j])$fatal(1,"logical/physical alias");
        end
    endtask
    initial begin
        counts[0]=1;counts[1]=2;counts[2]=3;counts[3]=5;counts[4]=6;
        counts[5]=127;counts[6]=128;counts[7]=129;counts[8]=2047;
        for(c=0;c<9;c=c+1)begin
            invalidate=1;@(negedge clk);invalidate=0;
            for(d=0;d<2;d=d+1)for(k=0;k<40;k=k+1)begin
                n=d ? counts[c]-1-k:k;
                candidates[0]=wrapped(n,counts[c]);candidates[1]=wrapped(n+1,counts[c]);
                candidates[2]=wrapped(n-1,counts[c]);candidates[3]=wrapped(n+2,counts[c]);candidates[4]=wrapped(n-2,counts[c]);
                visible[0]=candidates[2];visible[1]=candidates[0];visible[2]=candidates[1];visible[3]=candidates[3];
                fill();selections=selections+1;
            end
        end
        keys_valid=0;invalidate=1;@(negedge clk);invalidate=0;#1;
        if(want || dut.valid!=0)$fatal(1,"stale page candidate accepted");
        keys_valid=1;fill();enable=0;@(negedge clk);#1;
        if(dut.valid!=0 || want)$fatal(1,"disabled cache retained ownership");
        $display("PASS: %0d bidirectional/wrap selections, %0d fills, 9 count boundaries, no alias/visible eviction, invalidation/disable",selections,fills);$finish;
    end
    initial begin #1000000;$fatal(1,"cache watchdog");end
endmodule
