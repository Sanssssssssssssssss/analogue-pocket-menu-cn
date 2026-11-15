`timescale 1ns/1ps
module tb_psram_cache;
    reg clk=0;always #6.734 clk=~clk;
    reg enable=1,invalidate=0,begin_upload=0,write_en=0,request=0;
    reg [6:0] upload_slot=0;
    reg [27:0] write_addr=0;
    reg [15:0] write_data=0;
    reg [23:0] word_address=0;
    wire upload_ready,idle,done,fault;
    wire [31:0] data;
    wire [21:16] cram_a;
    wire [15:0] cram_dq;
    wire cram_clk,cram_adv_n,cram_cre,cram_ce0_n,cram_ce1_n,cram_oe_n,cram_we_n,cram_ub_n,cram_lb_n;
    integer physical_reads,physical_writes;
    coverflow_psram_cache dut(.cram_wait(1'b0),.*);
    sim_cellram memory(.a(cram_a),.dq(cram_dq),.clk(cram_clk),.adv_n(cram_adv_n),.cre(cram_cre),
        .ce0_n(cram_ce0_n),.ce1_n(cram_ce1_n),.oe_n(cram_oe_n),.we_n(cram_we_n),.ub_n(cram_ub_n),.lb_n(cram_lb_n),
        .reads(physical_reads),.writes(physical_writes));
    integer n,s,samples=0,waits;
    function [15:0] pattern(input integer slot,input integer offset);
        pattern=16'hc391^(slot<<5)^offset^(offset<<3);
    endfunction
    task read_word(input integer slot,input integer offset);
        begin
            @(negedge clk);word_address=(slot<<15)+offset;request=1;
            @(negedge clk);request=0;waits=0;
            while(!done)begin @(negedge clk);waits=waits+1;if(waits>160)$fatal(1,"CellRAM response ownership lost");end
            if(data!=={2{pattern(slot,offset)}} || fault)$fatal(1,"CellRAM word/address/queue mismatch slot=%d offset=%h data=%h",slot,offset,data);
            samples=samples+1;
        end
    endtask
    task upload(input integer slot);
        begin
            @(negedge clk);upload_slot=slot;begin_upload=1;
            @(negedge clk);begin_upload=0;
            for(n=0;n<22784;n=n+1)begin
                write_addr=28'h2000000+(slot<<16)+n*2;write_data=pattern(slot,n);write_en=1;
                @(negedge clk);write_en=0;repeat(n[0] ? 70:3)@(negedge clk);
                if(upload_ready && n!=22783)$fatal(1,"partially uploaded slot published");
                if(fault)$fatal(1,"PSRAM write queue overrun");
            end
            wait(upload_ready);repeat(3)@(negedge clk);
        end
    endtask
    initial begin
        repeat(16)@(negedge clk);upload(0);
        // APF DWORDs are spaced 75 clocks; the two halfwords arrive as a
        // four-clock burst, then a gap. Read ownership overlaps that stream.
        fork
            upload(127);
            begin
                repeat(20)@(negedge clk);
                for(s=0;s<3000;s=s+1)read_word(0,(s*43)%22784);
            end
        join
        for(s=0;s<22784;s=s+71)read_word(127,s);
        if(physical_writes!=45568 || physical_reads!=samples)$fatal(1,"physical transfer count differs");
        // Cancellation drops queued data but cannot steal a pending response.
        @(negedge clk);request=1;word_address=0;
        @(negedge clk);request=0;invalidate=1;
        @(negedge clk);invalidate=0;wait(done);repeat(4)@(negedge clk);
        if(!idle || fault || upload_ready)$fatal(1,"cancellation did not drain safely");
        $display("PASS: two full physical atlases including slot 127, %0d overlapped reads, bounded queue, pin timing and cancellation",samples);$finish;
    end
    initial begin #100000000;$fatal(1,"PSRAM watchdog");end
endmodule
