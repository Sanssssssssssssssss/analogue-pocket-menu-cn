`timescale 1ns/1ps
`include "paths.vh"
module tb_menu;
    reg clk=0;always #7 clk=~clk;
    reg ready=0;
    reg [31:0] buttons=0,ba=0,bd=0;
    reg bw=0,br=0;
    wire [31:0] param;
    wire rd,wr,op,fl;
    wire [15:0] slot;
    wire [31:0] off,address,length;
    reg done=1;reg [2:0] error=0;
    reg frame_ack=0,frame_started=0,frame_valid=0,visible=0,prepare_ready=1,load_ready=1;
    wire req,owned,show,rst,pause,new_load,finish_load,bound,fault;
    wire [7:0] code,state,first_code;wire [10:0] selected;
    reg [31:0] capacity=65536;
    gba_menu #(.TIMEOUT(34'd6000),.SETTLE_CYCLES(20'd16)) dut (
        .clk(clk),.ready(ready),.buttons(buttons),.bridge_wr(bw),.bridge_rd(br),
        .bridge_endian_little(1'b0),.bridge_addr(ba),.bridge_wr_data(bd),.param_rd_data(param),
        .t_read(rd),.t_write(wr),.t_open(op),.t_flush(fl),.t_slot(slot),.t_offset(off),.t_address(address),.t_length(length),
        .t_done(done),.t_error(error),.frame_ack(frame_ack),.frame_started(frame_started),.frame_valid(frame_valid),.frame_fault(1'b0),.visible(visible),
        .prepare_ready(prepare_ready),.load_ready(load_ready),.io_idle(1'b1),.save_capacity(capacity),
        .frame_request(req),.menu_owned(owned),.menu_show(show),.menu_reset(rst),.menu_pause(pause),
        .new_load(new_load),.finish_load(finish_load),.game_bound(bound),.fault(fault),.fault_code(code),.first_fault_code(first_code),.state(state),.selected(selected));
    reg [7:0] roots[0:2111],games[0:3135];
    initial begin $readmemh("root.hex",roots);$readmemh("games.hex",games);end
    integer page=0;
    reg [8*256-1:0] files[0:31];integer sizes[0:31],nf=0;
    reg [8*256-1:0] bindings[0:127];
    integer rom_reads=0,save_reads=0,rtc_reads=0,save_writes=0,rtc_writes=0,flushes=0,transactions=0;
    integer masks=0,ticks=0;
    integer frame_bytes=0,frame_origin=0,frame_chunks=0;
    reg fail_flush=0,hold_done=0;
    reg [7:0] pbytes[0:263];
    reg [8*256-1:0] path;
    reg [31:0] word,flags,size;
    integer i,w,fi,n,which;
    function integer find_file(input [8*256-1:0] name);
        integer j;begin find_file=-1;for(j=0;j<nf;j=j+1)if(files[j]==name)find_file=j;end
    endfunction
    task add_file(input [8*256-1:0] name,input integer bytes);
        begin files[nf]=name;sizes[nf]=bytes;nf=nf+1;end
    endtask
    function [7:0] pack_byte(input integer at);
        pack_byte=page==0 ? roots[at] : games[at];
    endfunction
    task read_word(input [31:0] addr,output [31:0] data);
        begin @(negedge clk);ba=addr;repeat(4)@(negedge clk);data=param;br=1;
            @(negedge clk);br=0;repeat(2)@(negedge clk);end
    endtask
    task reply(input [2:0] value);
        begin repeat(4)@(negedge clk);error=value;done=1;end
    endtask
    initial forever begin
        @(negedge clk);
        if(rd||wr||op||fl)begin
            if(!hold_done)begin
                done=0;error=0;
                if(op)begin
                    read_word(32'hF3000000,word);
                    for(w=0;w<66;w=w+1)begin
                        read_word(32'hF3000000+4*(w+1),word);
                        if(w<64)begin pbytes[4*w]=word[31:24];pbytes[4*w+1]=word[23:16];pbytes[4*w+2]=word[15:8];pbytes[4*w+3]=word[7:0];end
                        if(w==64)flags=word;if(w==65)size=word;
                    end
                    path=0;n=0;while(n<256&&pbytes[n]!=0)begin path={path[8*255-1:0],pbytes[n]};n=n+1;end
                    if(slot==100)begin
                        if(path=="/Assets/gbalab/common/menu.bin")page=0;
                        else if(path==`GAMES_PATH)page=1;
                        else $fatal(1,"wrong menu path '%0s'",path);
                    end
                    fi=find_file(path);
                    if(fi<0 && flags[0])begin add_file(path,size);fi=nf-1;reply(1);end
                    else if(fi<0)reply(3);
                    else begin if(flags[1])sizes[fi]=size;reply(0);end
                    if(fi>=0)bindings[slot]=path;
                end else if(rd)begin
                    if(slot==100 && (address[31:28]==6 || address[31:28]==7))begin
                        for(i=0;i<length;i=i+4)begin
                            @(negedge clk);bw=1;ba=address+i;
                            bd={pack_byte(off+i),pack_byte(off+i+1),pack_byte(off+i+2),pack_byte(off+i+3)};
                            @(negedge clk);bw=0;
                        end
                    end else if(slot==100 && address[31:28]==5)begin
                        if(visible || !owned)$fatal(1,"frame written while visible/game owns framebuffer");
                        // Bounded host adapter rejects oversized reads and requires
                        // contiguous file offsets and destination addresses.
                        if(length>16384 || length<4 || length%4 || address!=32'h50000000+frame_bytes)$fatal(1,"invalid frame chunk");
                        if(frame_bytes==0)frame_origin=off;
                        if(off!=frame_origin+frame_bytes)$fatal(1,"frame file offset gap");
                        frame_bytes=frame_bytes+length;frame_chunks=frame_chunks+1;
                        if(frame_bytes>76800)$fatal(1,"frame overflow");
                        repeat(80)@(negedge clk);
                        if(frame_bytes==76800)begin frame_ack=req;frame_valid=1;frame_bytes=0;end
                    end else if(slot==1)begin
                        if(address!=32'h10000000||length!=32768||!rst)$fatal(1,"unsafe ROM load");
                        rom_reads=rom_reads+1;
                        capacity=bindings[1]=="/Assets/gba/common/Second.gba" ? 131072 : 65536;
                    end else if(slot==10)begin
                        if(address!=32'h20000000||length!=capacity)$fatal(1,"save load mapping");save_reads=save_reads+1;
                    end else if(slot==11)begin
                        if(address!=32'h21000000||length!=16)$fatal(1,"RTC load mapping");rtc_reads=rtc_reads+1;
                    end else $fatal(1,"unexpected read slot %0d",slot);
                    reply(0);
                end else if(wr)begin
                    if(!bound || !pause || rst)$fatal(1,"save after resetting game");
                    if(slot==10 && address==32'h20000000 && length==capacity)save_writes=save_writes+1;
                    else if(slot==11 && address==32'h21000000 && length==16)rtc_writes=rtc_writes+1;
                    else $fatal(1,"wrong save write mapping");
                    reply(0);
                end else if(fl)begin
                    if(fail_flush)begin fail_flush=0;reply(4);end
                    else begin flushes=flushes+1;reply(0);end
                end
            end
            wait(!(rd||wr||op||fl));
        end
    end
    always @(negedge clk)begin
        ticks=ticks+1;
        if(ticks%16==0)visible=fault || (owned && show) || (!owned && bound);
    end
    always @(req)begin frame_started<=req;frame_valid<=0;end
    always @(posedge new_load)begin
        transactions=transactions+1;load_ready<=0;prepare_ready<=0;
        repeat(80)@(negedge clk);prepare_ready<=1;
    end
    always @(posedge finish_load)begin
        repeat(40)@(negedge clk);load_ready<=1;
    end
    always @(negedge clk)if(!owned && (!bound||rst||!load_ready))$fatal(1,"game released before loading/fence complete");
    task press(input integer key);
        begin @(negedge clk);buttons=32'd1<<key;repeat(4)@(negedge clk);buttons=0;repeat(4)@(negedge clk);end
    endtask
    task menu(input integer selection);
        begin wait(state==13 && selected==selection && visible);repeat(2)@(negedge clk);end
    endtask
    task running;
        begin wait(state==32 && !owned && bound);repeat(4)@(negedge clk);end
    endtask
    task open_pause;
        begin @(negedge clk);buttons=(1<<8)|(1<<9)|(1<<14);repeat(4)@(negedge clk);buttons=0;
            wait(state==34 && visible);repeat(2)@(negedge clk);end
    endtask
    task quit_game;
        begin open_pause;press(1);wait(state==34 && dut.pause_option==1);press(4);end
    endtask
    // Lose ownership just before paint, independently of boot initialization.
    initial begin wait(ready);wait(state==4);@(negedge clk);#1;dut.menu_owned=0;end
    initial begin
        add_file("/Assets/gbalab/common/menu.bin",0);add_file(`GAMES_PATH,0);
        add_file("/Assets/gba/common/First.gba",32768);add_file("/Assets/gba/common/Second.gba",32768);
        #100;ready=1;menu(0);
        press(4);menu(0);if(page!=1)$fatal(1,"A did not open GBA page");
        press(5);menu(0);if(page!=0)$fatal(1,"B did not return to Home");
        press(4);menu(0);press(4);running;
        if(transactions!=1||rom_reads!=1||save_reads!=0||rtc_reads!=0)$fatal(1,"first launch/create flow");
        open_pause;press(5);running;
        if(rst||transactions!=1)$fatal(1,"pause/resume reset game");
        fail_flush=1;quit_game;wait(fault);
        if(!bound||rst||!pause||code!=8'h54)$fatal(1,"flush failure discarded live progress");
        press(5);running;
        quit_game;menu(0);
        if(bound||!rst||flushes!=2||rtc_writes!=1)$fatal(1,"save/flush/return sequence");
        press(3);menu(1);press(4);running;
        if(transactions!=2||capacity!=131072)$fatal(1,"second ROM rearm/capacity");
        quit_game;menu(1);press(2);menu(0);press(4);running;
        if(transactions!=3||save_reads!=1||rtc_reads!=1||capacity!=65536)$fatal(1,"existing progress reload/rearm");
        quit_game;menu(0);
        // A malformed progress path is rejected before opening a ROM or save.
        games[64+32+256+7]="x";
        press(3);menu(1);press(2);wait(fault);
        if(code!=8'h13||rom_reads!=3||bound)$fatal(1,"unsafe save path was not rejected");
        press(5);menu(0);if(page!=0)$fatal(1,"error did not recover Home");
        hold_done=1;press(4);wait(fault);
        if(code!=8'hFE||bound||!rst)$fatal(1,"stale done accepted or timeout unsafe");
        if(first_code!=8'h54)$fatal(1,"retry overwrote first failure");
        if(frame_chunks<5 || frame_chunks%5)$fatal(1,"incomplete chunked frames");
        ready=0;hold_done=0;done=1;repeat(4)@(negedge clk);
        if(state!=0 || !owned || !rst || bound || first_code || code)$fatal(1,"APF Stop did not reset lifecycle");
        ready=1;menu(0);
        $display("PASS: boot/paint ownership recovery, Stop/Run reset, first-fault retention; bounded frames, A/B, three launches, 64K/128K, pause, save+RTC+flush, path rejection and timeout");
        $finish;
    end
    initial begin #10000000;$fatal(1,"watchdog state=%0d code=%h page=%0d selected=%0d",state,code,page,selected);end
endmodule
