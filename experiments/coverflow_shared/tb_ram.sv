`timescale 1ns/1ps
module tb_ram;
    reg wc=0,rc=0;always #5 wc=~wc;always #7 rc=~rc;
    reg we=0,ce=1;
    reg [9:0] wa=0,ra=0;
    reg [15:0] wd=0;
    wire [15:0] vendor,model,vendor_ce,model_ce;
    wire [11:0] tag_vendor,tag_model;
    picker_dpram #(.WIDTH(16),.ADDR(10)) original(.wclk(wc),.we(we),.waddr(wa),.wdata(wd),.rclk(rc),.raddr(ra),.q(vendor));
    coverflow_sim_ram #(.WIDTH(16),.ADDR(10)) portable(.wclk(wc),.we(we),.waddr(wa),.wdata(wd),.rclk(rc),.rce(1'b1),.raddr(ra),.q(model));
    coverflow_dpram_ce #(.WIDTH(16),.ADDR(10)) original_ce(.wclk(wc),.we(we),.waddr(wa),.wdata(wd),.rclk(rc),.rce(ce),.raddr(ra),.q(vendor_ce));
    coverflow_sim_ram #(.WIDTH(16),.ADDR(10)) portable_ce(.wclk(wc),.we(we),.waddr(wa),.wdata(wd),.rclk(rc),.rce(ce),.raddr(ra),.q(model_ce));
    picker_dpram #(.WIDTH(12),.ADDR(7)) original_tag(.wclk(wc),.we(we),.waddr(wa[6:0]),.wdata(wd[11:0]),.rclk(rc),.raddr(ra[6:0]),.q(tag_vendor));
    coverflow_sim_ram #(.WIDTH(12),.ADDR(7)) portable_tag(.wclk(wc),.we(we),.waddr(wa[6:0]),.wdata(wd[11:0]),.rclk(rc),.rce(1'b1),.raddr(ra[6:0]),.q(tag_model));
    integer n,comparisons=0;
    reg checking=0;
    always @(negedge rc)if(checking)begin
        if(vendor!==model || vendor_ce!==model_ce || tag_vendor!==tag_model)
            $fatal(1,"RAM mismatch address=%h ce=%b plain=%h/%h enabled=%h/%h tag=%h/%h",ra,ce,vendor,model,vendor_ce,model_ce,tag_vendor,tag_model);
        comparisons=comparisons+3;
    end
    initial begin
        repeat(16)@(negedge wc);
        for(n=0;n<1024;n=n+1)begin we=1;wa=n;wd=16'h9A53^(16'(n)*13);@(negedge wc);end
        we=0;repeat(16)@(negedge wc);checking=1;
        for(n=0;n<4096;n=n+1)begin
            @(posedge wc);ra=(n*137)%1024;ce=n%5!=4;
        end
        // With no writes, compare registered address latency and clock-enable
        // holds without invoking the vendor's DONT_CARE collision semantics.
        repeat(32)@(negedge rc);checking=0;
        $display("PASS: %0d RAM samples vs actual Intel model, 16-bit line/text and 12-bit tags, independent clocks, registered address and gated read hold",comparisons);$finish;
    end
    initial begin #200000;$fatal(1,"RAM validation watchdog");end
endmodule
