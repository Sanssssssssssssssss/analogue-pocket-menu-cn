`timescale 1ns/1ps
module tb_geometry;
    reg clk=0;always #5 clk=~clk;
    reg enabled=1,tick=0,go=0,direction=0;
    reg [10:0] selected=0,count=1;
    reg [3:0] title_target=8;
    wire [10:0] games[0:4];
    wire signed [10:0] x[0:3];wire [7:0] size[0:3];wire [4:0] brightness[0:3];wire [10:0] game[0:3];wire valid[0:3];
    wire anim,adir;wire [3:0] af,title_level;
    // Original control/SDRAM interfaces remain inactive. Its animation and
    // candidate-index calculation are the differential reference, not a model.
    cover_picker #(.CB(3)) reference(.clk_74a(clk),.enable(1'b0),.core_ready(1'b0),.cont1_key(32'd0),
        .clk_sys(clk),.clk_vid(clk),.sd_ce(1'b0),.pack_wr(1'b0),.pack_addr(28'd0),.pack_data(16'd0),
        .target_dataslot_done(1'b0),.target_dataslot_err(3'd0),.bridge_rd(1'b0),.bridge_wr(1'b0),
        .bridge_addr(32'd0),.bridge_wr_data(32'd0),.bridge_endian_little(1'b0),
        .ss_start_ok(1'b0),.ss_load_ok(1'b0),.sav_bytes(32'd0),.ss_bytes(32'd0),
        .sd_q(16'd0),.art_wr(1'b0),.art_waddr(24'd0),.art_wdata(16'd0),.dbg(16'd0),
        .cart_notify(32'd0),.cart_play(1'b0),.cprobe_done(1'b0),.cart_hdr(224'd0),.de(1'b0),.hs(1'b0),.vs(1'b0));
    genvar g;generate for(g=0;g<5;g=g+1)begin assign games[g]=reference.cgame[g];end endgenerate
    coverflow_geometry dut(.clk_74a(clk),.enable(enabled),.frame_tick(tick),.ago(go),.ago_dir(direction),
        .tl_target(title_target),.rcount(count),.cgame(games),.anim(anim),.adir(adir),.af(af),.tlevel(title_level),
        .x(x),.size(size),.brightness(brightness),.game(game),.valid(valid));
    integer checks=0,i,j,n,case_id,c,step_id;reg check=0;
    always @(negedge clk)if(check)begin
        if({anim,adir,af,title_level}!=={reference.anim,reference.adir,reference.af,reference.tlevel})$fatal(1,"animation state diverged");
        for(j=0;j<4;j=j+1)begin
            if({x[j],size[j],brightness[j],game[j],valid[j]}!=={reference.cx[j],reference.cs[j],reference.cb[j],reference.cg[j],reference.cv[j]})
                $fatal(1,"CoverFlow differs count=%0d index=%0d frame=%0d slot=%0d",count,selected,af,j);
            checks=checks+1;
        end
    end
    task frame;
        begin @(negedge clk);tick=1;@(negedge clk);tick=0;repeat(4)@(negedge clk);end
    endtask
    initial begin
        force reference.count=count;force reference.idx=selected;force reference.frame_tick=tick;
        force reference.ago=go;force reference.ago_dir=direction;force reference.tl_target=title_target;
        for(case_id=0;case_id<8;case_id=case_id+1)begin
            case(case_id)0:c=1;1:c=2;2:c=3;3:c=5;4:c=127;5:c=128;6:c=129;default:c=2047;endcase
            count=c;selected=0;repeat(160)@(negedge clk);check=1;
            for(step_id=0;step_id<12;step_id=step_id+1)begin
                direction=step_id%2;
                selected=direction ? (selected==0 ? count-1:selected-1):(selected+1>=count ? 0:selected+1);
                repeat(160)@(negedge clk);go=1;@(negedge clk);go=0;
                for(n=0;n<10;n=n+1)frame;
            end
            check=0;
        end
        enabled=0;repeat(4)@(negedge clk);if(anim || af || title_level)$fatal(1,"disabled state not cleared");
        $display("PASS: %0d per-cover comparisons to unmodified GB/GBC CoverFlow, 8 count boundaries, 96 bidirectional animations; disabled-state reset",checks);$finish;
    end
    initial begin #10000000;$fatal(1,"geometry watchdog");end
endmodule
