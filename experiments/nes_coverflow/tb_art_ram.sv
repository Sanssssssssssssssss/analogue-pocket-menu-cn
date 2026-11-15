`timescale 1ns/1ps
module tb_art_ram;
    reg clk=0;always #5 clk=~clk;
    reg enable=1,invalidate=0,begin_upload=0,write_en=0,request=0;
    reg [2:0] upload_slot=0;
    reg [27:0] write_addr=0;
    reg [15:0] write_data=0;
    reg [23:0] word_address=0;
    wire upload_ready,done,fault;wire [31:0] data;
    nes_coverflow_art_ram dut(.*);
    integer s,n,reads=0;
    function [15:0] pattern(input integer slot,input integer offset);
        pattern=(slot*16'h3917)^offset^(offset<<3);
    endfunction
    task begin_slot(input integer slot);
        begin @(negedge clk);upload_slot=slot;begin_upload=1;@(negedge clk);begin_upload=0;end
    endtask
    task read_word(input integer slot,input integer offset);
        begin
            @(negedge clk);word_address=(slot<<15)+offset;request=1;
            @(negedge clk);request=0;wait(done);#1;
            if(data!={pattern(slot,offset|1),pattern(slot,offset&~1)})$fatal(1,"packed RAM alias slot=%d offset=%d data=%h",slot,offset,data);
            reads=reads+1;
        end
    endtask
    initial begin
        for(s=0;s<5;s=s+1)begin
            begin_slot(s);
            for(n=0;n<22784;n=n+1)begin
                if(upload_ready)$fatal(1,"partial image published");
                write_addr=28'h2000000+(s<<16)+n*2;write_data=pattern(s,n);write_en=1;
                @(negedge clk);
            end
            write_en=0;#1;if(!upload_ready || fault)$fatal(1,"complete atlas rejected");
        end
        for(s=0;s<5;s=s+1)for(n=0;n<22784;n=n+2)read_word(s,n);
        // An out-of-order write cannot publish a partially replaced slot.
        begin_slot(2);write_addr=28'h2020004;write_data=16'hffff;write_en=1;
        @(negedge clk);write_en=0;#1;
        if(!fault || upload_ready)$fatal(1,"discontinuous upload accepted");
        invalidate=1;@(negedge clk);invalidate=0;#1;
        if(fault || upload_ready)$fatal(1,"invalidate failed");
        begin_slot(1);enable=0;@(negedge clk);#1;
        if(dut.receiving || upload_ready)$fatal(1,"disabled upload retained ownership");
        $display("PASS: five full RGB565 128/80 atlases, %0d DWORD reads, packed slot/mip edges, incomplete upload guard and cancellation",reads);$finish;
    end
    initial begin #10000000;$fatal(1,"RAM watchdog");end
endmodule
