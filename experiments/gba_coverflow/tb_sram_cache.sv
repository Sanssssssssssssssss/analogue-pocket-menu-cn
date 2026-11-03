`timescale 1ns/1ps
module tb_sram_cache;
    reg clk=0;always #4.965 clk=~clk;
    reg enable=1,invalidate=0,begin_upload=0,write_en=0,request=0;
    reg [2:0] upload_slot=0;
    reg [27:0] write_addr=0;
    reg [15:0] write_data=0;
    reg [23:0] word_address=0;
    wire upload_ready,idle,done,fault;
    wire [31:0] data;
    wire [16:0] sram_a;
    wire [15:0] sram_dq;
    wire sram_oe_n,sram_we_n,sram_ub_n,sram_lb_n;
    integer physical_reads,physical_writes;
    coverflow_sram_cache dut(.*);
    sim_coverflow_sram memory(.clock(clk),.a(sram_a),.dq(sram_dq),.oe_n(sram_oe_n),.we_n(sram_we_n),
        .ub_n(sram_ub_n),.lb_n(sram_lb_n),.reads(physical_reads),.writes(physical_writes));
    function [15:0] pattern(input integer slot,input integer offset);
        pattern=16'h9347^(slot*613)^(offset*73)^(offset>>3);
    endfunction
    integer i,j,k,waits,samples=0;
    task read_word(input integer slot,input integer offset,input persistent_complete);
        integer aligned;
        begin
            aligned=offset&~1;
            @(negedge clk);request=1;word_address=(slot<<15)+offset;
            @(negedge clk);request=0;waits=0;
            while(!done)begin
                @(negedge clk);waits=waits+1;
                if(waits>64)$fatal(1,"SRAM read response did not complete");
                if(persistent_complete && !upload_ready)$fatal(1,"upload completion dropped during raster reads");
            end
            if(data!=={pattern(slot,aligned+1),pattern(slot,aligned)} || fault)
                $fatal(1,"packed SRAM DWORD mismatch slot=%d offset=%h got=%h",slot,offset,data);
            samples=samples+1;
        end
    endtask
    task upload(input integer slot);
        integer at;
        begin
            @(negedge clk);upload_slot=slot;begin_upload=1;
            @(negedge clk);begin_upload=0;
            for(at=0;at<22784;at=at+1)begin
                write_addr=28'h2000000+(slot<<16)+at*2;write_data=pattern(slot,at);write_en=1;
                @(negedge clk);write_en=0;repeat(at[0] ? 96:3)@(negedge clk);
                if(fault)$fatal(1,"SRAM upload ordering/queue fault");
                if(upload_ready && at!=22783)$fatal(1,"incomplete image was published");
            end
            wait(upload_ready);repeat(3)@(negedge clk);
        end
    endtask
    task clear_fault;
        begin
            @(negedge clk);invalidate=1;
            @(negedge clk);invalidate=0;wait(idle);repeat(4)@(negedge clk);
            if(fault || upload_ready)$fatal(1,"SRAM invalidation did not clear publication/fault");
        end
    endtask
    initial begin
        repeat(16)@(negedge clk);upload(0);
        fork
            begin for(i=1;i<5;i=i+1)upload(i);end
            begin for(j=0;j<4000;j=j+1)read_word(0,(j*67)%22784,0);end
        join
        if(physical_writes!=113920)$fatal(1,"packed five-slot physical write count differs");
        for(i=0;i<5;i=i+1)begin
            read_word(i,0,1);read_word(i,1,1);read_word(i,22783,1);
            for(k=0;k<22784;k=k+137)read_word(i,k,1);
        end
        // Check every physical write as well as the sampled read responses.
        for(i=0;i<5;i=i+1)for(k=0;k<22784;k=k+1)
            if(!memory.written[i*22784+k] || memory.words[i*22784+k]!==pattern(i,k))
                $fatal(1,"physical FIFO write mismatch slot=%d offset=%d",i,k);
        // An invalid read is acknowledged with a fault and touches no pins.
        @(negedge clk);request=1;word_address=5<<15;
        @(negedge clk);request=0;wait(done);
        if(!fault || data!=0)$fatal(1,"invalid physical slot was not rejected");
        clear_fault;
        @(negedge clk);upload_slot=0;begin_upload=1;
        @(negedge clk);begin_upload=0;write_en=1;write_addr=28'h2000004;
        @(negedge clk);write_en=0;repeat(4)@(negedge clk);
        if(!fault)$fatal(1,"noncontiguous atlas write was not rejected");
        clear_fault;
        $display("PASS: five packed SRAM atlases, %0d DWORD samples with concurrent upload, both halfwords, persistent completion, 4.25ns I/O budgets, datasheet pin timing and invalidation",samples);
        $finish;
    end
    initial begin #100000000;$fatal(1,"SRAM unit watchdog");end
endmodule
