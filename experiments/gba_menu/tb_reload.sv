`timescale 1ns/1ps
module tb_reload;
    reg bc=0,mc=0;always #7 bc=~bc;always #23 mc=~mc;
    reg wr=0,finish=0,start=0,reset=1,ready=1,fence_ready=0;
    reg [31:0] addr=0,data=0;
    wire valid,fv,fd,busy,flash,id_valid;wire [1:0] dest;wire [27:0] wa;wire [15:0] wd;wire [31:0] id;
    apf_write_ingress dut (
        .clk_74a(bc),.clk_memory(mc),.bridge_wr(wr),.bridge_endian_little(1'b0),
        .bridge_addr(addr),.bridge_wr_data(data),.completion_request(finish),.transaction_start(start),
        .write_valid(valid),.write_dest(dest),.write_addr(wa),.write_data(wd),.write_ready(ready),
        .fence_valid(fv),.fence_ready(fence_ready),.fence_done(fd),.write_busy(busy));
    save_type_detector detector(mc,reset,valid && ready && dest==1,wd,wa,flash,id,id_valid);
    wire rtc_complete,sv,lv;wire [31:0] timestamp;wire [41:0] savedtime;
    rtc_persistence rtc (
        .clk(mc),.reset_n(!reset),.loader_accept(valid && ready && dest==2),
        .loader_addr(wa),.loader_data(wd),.save_size(flash ? 24'd131072 : 24'd65536),
        .finalize_load(fd),.host_epoch(32'd1700000000),.host_savedtime(42'd0),
        .loaded_timestamp(timestamp),.loaded_savedtime(savedtime),.load_complete(rtc_complete),
        .sidecar_record_valid(sv),.legacy_record_valid(lv));
    integer words=0,fences=0,round;
    always @(posedge mc)begin
        if(valid && ready)words=words+1;
        if(fd)fences=fences+1;
    end
    task send(input [31:0] a,input [31:0] d);
        begin @(negedge bc);addr=a;data=d;wr=1;@(negedge bc);wr=0;repeat(220)@(negedge bc);end
    endtask
    task begin_game;
        begin
            @(negedge bc);start=1;reset=1;@(negedge bc);start=0;
            repeat(8)@(negedge mc);reset=0;
            if(flash || id_valid || rtc_complete)$fatal(1,"per-game state leaked");
        end
    endtask
    reg [45:0] held;
    initial begin
        repeat(8)@(negedge mc);reset=0;
        // Initial external BIOS download drains normally without closing a
        // game transaction. Only the menu's final ROM/save/RTC step fences.
        send(32'h30000000,32'h060000ea);
        if(fences)$fatal(1,"BIOS download unexpectedly closed the game transaction");
        for(round=1;round<=3;round=round+1)begin
            begin_game;ready=0;
            fork
                send(32'h100000ac,32'h54455354);
                begin
                    wait(valid);@(negedge mc);held={dest,wa,wd};
                    repeat(12)begin @(negedge mc);if(!valid||{dest,wa,wd}!==held)$fatal(1,"backpressure corrupted word");end
                    ready=1;
                end
            join
            send(32'h100000b0,0);
            if(round==2)begin
                send(32'h10000100,32'h464c4153);send(32'h10000104,32'h48314d5f);send(32'h10000108,32'h56000000);
            end
            send(32'h20000000,32'h12345678);
            // An incomplete RTC sidecar is ignored, then reset for the next game.
            if(round==2)send(32'h21000000,32'hdeadbeef);
            if(flash!==(round==2) || id!==32'h54455354 || !id_valid)$fatal(1,"save detector/header mismatch");
            fence_ready=0;@(negedge bc);finish=1;@(negedge bc);finish=0;
            wait(fv);repeat(12)@(negedge mc);
            if(fences!=round-1||rtc_complete)$fatal(1,"fence overtook physical write/RTC");
            fence_ready=1;wait(fences==round);wait(rtc_complete);
            if(sv||lv || timestamp!=1700000000)$fatal(1,"RTC fallback/reset mismatch");
            repeat(12)@(negedge mc);
        end
        if(words!=28)$fatal(1,"missing real ingress words %0d",words);
        $display("PASS: actual patched ingress, Intel FIFO, three loads/fences, backpressure, per-game FLASH1M/header and RTC reset");$finish;
    end
    initial begin #1000000;$fatal(1,"reload watchdog");end
endmodule
