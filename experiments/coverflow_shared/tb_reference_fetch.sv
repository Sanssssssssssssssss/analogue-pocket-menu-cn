`timescale 1ns/1ps
module tb_reference_fetch;
    reg clk=0;always #5 clk=~clk;
    reg [2:0] phase=0;always @(posedge clk)phase<=phase+1'b1;
    reg [15:0] data=0;
    reg request_toggle=0;
    reg [8:0] request_y=0;
    cover_picker #(.CB(3)) reference(.clk_74a(clk),.enable(1'b0),.core_ready(1'b0),.cont1_key(32'd0),
        .clk_sys(clk),.clk_vid(1'b0),.sd_ce(phase==0),.pack_wr(1'b0),.pack_addr(28'd0),.pack_data(16'd0),
        .target_dataslot_done(1'b0),.target_dataslot_err(3'd0),.bridge_rd(1'b0),.bridge_wr(1'b0),
        .bridge_addr(32'd0),.bridge_wr_data(32'd0),.bridge_endian_little(1'b0),
        .ss_start_ok(1'b0),.ss_load_ok(1'b0),.sav_bytes(32'd0),.ss_bytes(32'd0),
        .sd_q(data),.art_wr(1'b0),.art_waddr(24'd0),.art_wdata(16'd0),.dbg(16'd0),
        .cart_notify(32'd0),.cart_play(1'b0),.cprobe_done(1'b0),.cart_hdr(224'd0),.de(1'b0),.hs(1'b0),.vs(1'b0));
    function [15:0] color(input [23:0] a);color=a[15:0]^16'hA59C;endfunction
    always @(posedge clk)if(reference.tick)data<=color(reference.sd_addr-24'h400000);
    integer n,writes=0;
    always @(posedge clk)if(reference.lb_we && reference.fy==67)begin
        // The frozen expression mixes signed coordinates with an unsigned LUT
        // value. -14 is widened as an unsigned 11-bit value (2034), producing
        // (-2034*276) mod 2^18 = 225048 instead of 14*276 = 3864.
        if(reference.lb_wa[8:0]!=writes || reference.lb_wd!==color((3<<15)+16384+8*80+((225048+writes*276)>>8)))
            $fatal(1,"legacy clipping witness changed x=%d raw=%h step=%d base=%h",reference.lb_wa[8:0],reference.lb_wd,reference.fstep,reference.fbase);
        writes=writes+1;
    end
    initial begin
        force reference.hold_gb=1;force reference.picker_download=0;
        force reference.hc=1;force reference.vc=10;
        force reference.lreq_t=request_toggle;force reference.lreq_y=request_y;
        for(n=0;n<4;n=n+1)begin reference.vx[n]=-14;reference.vs_[n]=74;reference.vg[n]=3;reference.vv[n]=n==0;reference.vl[n]=1;end
        repeat(80)@(negedge clk);request_y=0;request_toggle=1;
        repeat(40)@(negedge clk);wait(reference.fst==0);
        request_y=67;request_toggle=0;repeat(40)@(negedge clk);wait(reference.fst==0);repeat(20)@(negedge clk);
        if(writes!=60)$fatal(1,"incomplete reference scanline %d",writes);
        $display("CONFIRMED: actual frozen GB/GBC fetcher has unsigned clipped-coordinate wrap; 60 legacy samples match the witness. New transport separately tests the correct signed coordinates.");$finish;
    end
    initial begin #200000;$fatal(1,"reference fetch watchdog");end
endmodule
