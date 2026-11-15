// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_pm_cpu;
    reg clk=0;
    always #15.625002441 clk=~clk;
    // Independent exhaustive oracle is the verbatim upstream combinational ALU.
    reg [15:0] test_a=0;
    reg [7:0] test_b=1;
    reg test_size=0;
    wire [15:0] test_r, reference_r;
    wire [3:0] test_f, reference_f;
    reg [15:0] delayed_a [0:7];
    reg [7:0] delayed_b [0:7];
    reg delayed_size [0:7];
    pm_divide pipeline(clk,test_a,test_b,test_size,test_r,test_f);
    alu_ref reference_alu(5'd21,delayed_size[7],delayed_a[7],{8'd0,delayed_b[7]},1'b0,1'b0,reference_r,reference_f);
    integer t;
    always @(posedge clk) begin
        delayed_a[0]<=test_a; delayed_b[0]<=test_b; delayed_size[0]<=test_size;
        for(t=1;t<8;t=t+1)begin
            delayed_a[t]<=delayed_a[t-1];delayed_b[t]<=delayed_b[t-1];delayed_size[t]<=delayed_size[t-1];
        end
    end
    integer exhaustive_count=0, zero_count=0, supplied=0;
    reg exhaustive_done=0;
    task automatic compare_divide;
        if(supplied>=8)begin
            if(test_f !== reference_f)$fatal(1,"DIV flags mismatch A=%h B=%h size=%b got=%h expected=%h",delayed_a[7],delayed_b[7],delayed_size[7],test_f,reference_f);
            if(delayed_b[7]!=0)begin
                if(test_r !== reference_r)$fatal(1,"DIV result mismatch A=%h B=%h got=%h expected=%h",delayed_a[7],delayed_b[7],test_r,reference_r);
                exhaustive_count=exhaustive_count+1;
            end else zero_count=zero_count+1;
        end
    endtask
    task automatic drive_divide(input [15:0] a,input[7:0] b,input sz);
        @(negedge clk); test_a=a;test_b=b;test_size=sz;
        @(posedge clk); #1; supplied=supplied+1; compare_divide();
    endtask
    integer a,b,sz;
    initial begin
        for(sz=0;sz<2;sz=sz+1)
            for(b=1;b<256;b=b+1)
                for(a=0;a<65536;a=a+1)drive_divide(a[15:0],b[7:0],sz[0]);
        for(a=0;a<256;a=a+1)drive_divide({a[7:0],~a[7:0]},0,a[0]);
        repeat(7)drive_divide(16'd0,0,0);
        if(exhaustive_count!=33423360 || zero_count!=256)$fatal(1,"Exhaustive coverage %0d/%0d",exhaustive_count,zero_count);
        $display("PASS DIV 33423360 native nonzero operand/size combinations; 256 zero-divisor flag cases; input changes every clock");
        exhaustive_done=1;
    end

    // Both unmodified and pipelined CPUs execute the same synthetic ROM and
    // actual native microcode at the native 16-system-clock enable interval.
    reg [3:0] prescale=0;
    reg paused=0,reset=1,bus_request=0;
    wire ce=&prescale && !paused;
    always @(posedge clk)prescale<=prescale+1'b1;
    reg [7:0] memory [0:65535];
    wire [23:0] address_new,address_ref;
    wire [7:0] dout_new,dout_ref;
    wire [1:0] bus_new,bus_ref,i01_new,i01_ref;
    wire pk_new,pk_ref,pl_new,pl_ref,read_new,read_ref,vector_new,vector_ref;
    wire write_new,write_ref,sync_new,sync_ref,ack_new,ack_ref,dma_new,dma_ref;
    wire [7:0] din_new=memory[address_new[15:0]],din_ref=memory[address_ref[15:0]];
    s1c88 dut(clk,ce,reset,din_new,4'd0,4'd0,pk_new,pl_new,i01_new,dout_new,address_new,bus_new,read_new,vector_new,write_new,sync_new,ack_new,bus_request,dma_new);
    s1c88_ref original(clk,ce,reset,din_ref,4'd0,4'd0,pk_ref,pl_ref,i01_ref,dout_ref,address_ref,bus_ref,read_ref,vector_ref,write_ref,sync_ref,ack_ref,bus_request,dma_ref);
    integer cycles=0, checked_edges=0, div_commits=0, mul_commits=0, dma_edges=0, pause_cycles=0;
    integer last_operand_change=0, min_div_age=1000000;
    reg [31:0] previous_operands=0;
    reg cpu_done=0;
    task automatic check_cpu;
        if(!reset && cycles>100 && !cpu_done)begin
            if({address_new,dout_new,bus_new,pk_new,pl_new,i01_new,read_new,vector_new,write_new,sync_new,ack_new,dma_new} !==
               {address_ref,dout_ref,bus_ref,pk_ref,pl_ref,i01_ref,read_ref,vector_ref,write_ref,sync_ref,ack_ref,dma_ref})
                $fatal(1,"CPU bus edge mismatch cycle=%0d PC=%h micro=%0d new=%h ref=%h",cycles,dut.PC,dut.microaddress+dut.microprogram_counter,address_new,address_ref);
            if({dut.BA,dut.HL,dut.IX,dut.IY,dut.SP,dut.PC,dut.SC,dut.EP,dut.NB,dut.CB,dut.XP,dut.YP,dut.BR} !==
               {original.BA,original.HL,original.IX,original.IY,original.SP,original.PC,original.SC,original.EP,original.NB,original.CB,original.XP,original.YP,original.BR})
                $fatal(1,"CPU register mismatch cycle=%0d PC=%h micro=%0d HL=%h/%h SC=%h/%h",cycles,dut.PC,dut.microaddress+dut.microprogram_counter,dut.HL,original.HL,dut.SC,original.SC);
            checked_edges=checked_edges+1;
        end
    endtask
    always @(posedge clk)begin
        cycles=cycles+1;
        if(paused)pause_cycles=pause_cycles+1;
        #1;check_cpu();
    end
    always @(negedge clk)begin
        if(ce && !reset && !cpu_done)begin
            if(dut.pk && dut.state==dut.STATE_EXECUTE && !dut.bus_ack && dut.alu_flag_update)begin
                if(dut.alu_op==21)begin
                    if(cycles-last_operand_change<8)$fatal(1,"DIV consumed before eight clocks");
                    if(cycles-last_operand_change<min_div_age)min_div_age=cycles-last_operand_change;
                    div_commits=div_commits+1;
                end
                if(dut.alu_op==22)mul_commits=mul_commits+1;
            end
            if(dma_new)dma_edges=dma_edges+1;
        end
        #1;check_cpu();
        if({dut.alu_A,dut.alu_B}!==previous_operands)begin
            previous_operands={dut.alu_A,dut.alu_B};last_operand_change=cycles;
        end
    end
    integer i,p,seed=32'h734591ad;
    reg [15:0] numerator;
    reg [7:0] denominator_value;
    task automatic emit(input [7:0] v);memory[p]=v;p=p+1;endtask
    initial begin
        for(i=0;i<65536;i=i+1)memory[i]=8'hff;
        memory[0]=0;memory[1]=1;p=256;
        for(i=0;i<1024;i=i+1)begin
            seed=(seed*1664525)+1013904223;
            numerator=i<8 ? (16'hffff>>i) : seed[31:16];
            denominator_value=i<255 ? (i+1) : ((seed[7:0]==0)?8'd1:seed[7:0]);
            emit(8'hc5);emit(numerator[7:0]);emit(numerator[15:8]);
            emit(8'hc4);emit(denominator_value);emit(8'd0);
            emit(8'hce);emit(8'hd9); // DIV HL,A from the pinned translation ROM.
            emit(8'hce);emit(8'hd8); // Native MUL, to check adjacent ALU selection.
            emit(8'h00); // Native ADD, keeps the ordinary half-cycle ALU path.
        end
        emit(8'hce);emit(8'hae); // HALT.
        repeat(8)begin @(negedge clk);wait(ce);end
        @(negedge clk);#2;reset=0;
        wait(div_commits>=4);
        // Stop clock enables with an in-flight divide, then resume. Arithmetic
        // pipeline keeps settling, exactly like the old combinational ALU.
        wait(dut.alu_op==21 && !ce);#2;paused=1;
        repeat(91)@(posedge clk);
        @(negedge clk);#2;paused=0;
        wait(div_commits>=8);
        @(negedge clk);#2;bus_request=1;
        repeat(131)@(posedge clk);
        @(negedge clk);#2;bus_request=0;
        wait(div_commits>=1024);
        wait(dut.state==dut.STATE_HALT);
        if(mul_commits!=1024 || dma_edges<2 || pause_cycles!=91)$fatal(1,"Missing CPU scenario coverage mul=%0d DMA=%0d pause=%0d",mul_commits,dma_edges,pause_cycles);
        cpu_done=1;
        $display("PASS CPU native microcode lockstep: %0d edges, %0d DIV, %0d MUL, DMA=%0d, paused clocks=%0d, minimum operand age=%0d clocks",checked_edges,div_commits,mul_commits,dma_edges,pause_cycles,min_div_age);
    end
    initial begin
        wait(cpu_done && exhaustive_done);
        $display("PASS Mini CPU pipeline suite");$finish;
    end
    initial begin
        #1500000000;
        $fatal(1,"Timeout PC=%h DIV=%0d exhaustive=%0d",dut.PC,div_commits,exhaustive_count);
    end
endmodule
