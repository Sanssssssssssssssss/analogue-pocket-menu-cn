`timescale 1ns/1ps
// Differential raster test against the actual device-tested GB/GBC source.
// Only selection/animation state and synthetic card contents are supplied here.
module tb_view;
    parameter GAPS=0;
    parameter SHOWCASE=0;
    parameter SANITY_ONLY=0;
    parameter ASYNC_BRIDGE=0;
    reg clk=0,sys=0,vid=0;
    always #1.35 clk=~clk;
    always #1 sys=~sys;
    always #(GAPS ? 12:15) vid=~vid;
    integer phase=0;
    reg ce=1;
    always @(negedge vid)begin
        phase=(phase+1)%5;
        ce=!(GAPS && phase==4);
    end
    wire ref_vid=vid && ce;
    reg [10:0] selected=0,total=5;
    reg animated=0,direction=0;
    reg [3:0] pose=0;
    reg cache_commit=0,text_we=0;
    reg [10:0] cache_game=0;
    reg [9:0] text_addr=0;
    reg [15:0] text_data=0;
    reg [2:0] sdphase=0;
    always @(posedge sys)sdphase<=sdphase+1'b1;
    reg [15:0] ref_data=0;
    wire request,idle,underrun,fault;
    wire [23:0] address,rgb;
    wire source_request,source_done,bridge_fault,view_fault;
    wire [23:0] source_address;
    wire [31:0] source_data;
    generate if(ASYNC_BRIDGE)begin:async_memory
        coverflow_memory_bridge bridge(.source_clock(clk),.memory_clock(sys),.source_request(source_request),.source_word_address(source_address),
            .source_done(source_done),.source_data(source_data),.source_idle(),.source_fault(bridge_fault),
            .memory_request(request),.memory_word_address(address),.memory_done(done),.memory_data(data));
    end else begin:direct_memory
        assign request=source_request;assign address=source_address;assign source_done=done;assign source_data=data;assign bridge_fault=0;
    end endgenerate
    assign fault=view_fault || bridge_fault;
    wire de,hs,vs,skip;
    reg done=0;
    reg [31:0] data=0;
    reg outstanding=0;
    reg [23:0] saved_address=0;
    integer latency=0,requests=0;
    reg [15:0] showcase_art[0:163839];
    reg [15:0] showcase_text[0:1023];
    initial if(SHOWCASE)begin $readmemh("showcase-art.hex",showcase_art);$readmemh("showcase-text.hex",showcase_text);end
    function [15:0] texture(input [23:0] a);
        // Each slot, mip, source row and source column has a distinct color.
        texture=SHOWCASE ? showcase_art[a] : {a[4:0]^a[19:15],a[10:5]^a[16:11],a[14:10]^a[4:0]};
    endfunction
    always @(posedge sys)begin
        done<=0;
        if(reference.tick)ref_data<=texture(reference.sd_addr-24'h400000);
        if(request)begin
            if(outstanding)$fatal(1,"overlapping texture requests");
            outstanding<=1;saved_address<=address;
            latency<=2+(requests%11);requests<=requests+1;
        end else if(outstanding)begin
            if(latency==0)begin
                data<={texture({saved_address[23:1],1'b1}),texture({saved_address[23:1],1'b0})};
                done<=1;outstanding<=0;
            end else latency<=latency-1;
        end
    end
    cover_picker #(.CB(3)) reference(.clk_74a(clk),.enable(1'b0),.core_ready(1'b0),.cont1_key(32'd0),
        .clk_sys(sys),.clk_vid(ref_vid),.sd_ce(sdphase==0),.pack_wr(ref_bitmap_write),.pack_addr({12'd0,ref_bitmap_address}),.pack_data(text_data),
        .target_dataslot_done(1'b0),.target_dataslot_err(3'd0),.bridge_rd(1'b0),.bridge_wr(1'b0),
        .bridge_addr(32'd0),.bridge_wr_data(32'd0),.bridge_endian_little(1'b0),
        .ss_start_ok(1'b0),.ss_load_ok(1'b0),.sav_bytes(32'd0),.ss_bytes(32'd0),
        .sd_q(ref_data),.art_wr(1'b0),.art_waddr(24'd0),.art_wdata(16'd0),.dbg(16'd0),
        .cart_notify(32'd0),.cart_play(1'b0),.cprobe_done(1'b0),.cart_hdr(224'd0),.de(1'b0),.hs(1'b0),.vs(1'b0));
    coverflow_view #(.CB(3)) dut(.clk_74a(clk),.clk_sys(ASYNC_BRIDGE ? clk:sys),.clk_vid(vid),.pixel_ce(ce),
        .enable(1'b1),.hold_gb(1'b1),.menu_active(1'b1),.vs(1'b0),
        .ago(1'b0),.ago_dir(1'b0),.invalidate(1'b0),.cache_commit(cache_commit),.cache_game(cache_game),
        .idx(selected),.count(total),.level_target(4'd8),.tl_target(4'd8),.htw(9'd64),.hsw(9'd0),.gen(1'b0),
        .text_we(text_we),.text_addr(text_addr),.text_data(text_data),
        .hr_rgb(rgb),.hr_de(de),.hr_hs(hs),.hr_vs(vs),.hr_skip(skip),
        .mem_req(source_request),.mem_word_addr(source_address),.mem_done(source_done),.mem_data(source_data),.mem_idle(idle),.underrun(underrun),.fault(view_fault));
    reg ref_tag_we=0;
    reg [2:0] ref_tag_addr=0;
    reg [11:0] ref_tag_data=0;
    wire ref_bitmap_write=text_we && text_addr<512;
    wire [15:0] ref_bitmap_address={6'd4,text_addr[8:0],1'b0};
    reg checking=0,sample_ce,previous_hs=0,previous_vs=0;
    integer comparisons=0,pixels=0,frames=0,fd=0,i;
    reg [9:0] sanity_address=0;
    always @(posedge vid)begin
        sample_ce=ce;
        #0.1;
        if(hs && previous_hs)$fatal(1,"HS lasted multiple physical clocks");
        if(vs && previous_vs)$fatal(1,"VS lasted multiple physical clocks");
        if(skip && !de)$fatal(1,"SKIP asserted outside active pixels");
        if(checking && sample_ce)begin
            if({de,hs,vs}!=={reference.hr_de,reference.hr_hs,reference.hr_vs})
                $fatal(1,"video sync differs hc=%0d vc=%0d",dut.hc,dut.vc);
            if(rgb!==reference.hr_rgb)begin
                $display("samples new=%h reference=%h slot0 geometry new=(%d,%d,%d,%b,%b) reference=(%d,%d,%d,%b,%b)",dut.s2_pix,reference.s2_pix,
                    dut.vx[0],dut.vs_[0],dut.vg[0],dut.vv[0],dut.vl[0],reference.vx[0],reference.vs_[0],reference.vg[0],reference.vv[0],reference.vl[0]);
                $display("reference fetch frame slot0=(%d,%d,%d) line=%d step=%d rowbase=%h; new slot0=(%d,%d,%d) line=%d step=%d rowbase=%h",
                    reference.fx[0],reference.fs_[0],reference.fg[0],reference.fy,reference.fstep,reference.fbase,
                    dut.fetcher.x[0],dut.fetcher.size[0],dut.fetcher.game[0],dut.fetcher.y,dut.fetcher.source_step,dut.fetcher.row_base);
                $fatal(1,"pixel differs pose=%0d dir=%0d gaps=%0d hc=%0d vc=%0d new=%06h accepted=%06h line_ready=%0d",pose,direction,GAPS,dut.hc,dut.vc,rgb,reference.hr_rgb,dut.line_ready);
            end
            comparisons=comparisons+1;
            if(de)begin
                pixels=pixels+1;
                if(fd)$fwrite(fd,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);
            end
        end
        previous_hs=hs;previous_vs=vs;
    end
    task one_frame(input integer id);
        integer slot;
        begin
            // Reassert each pose explicitly: Verilator 5.020 evaluates a
            // procedural force's RHS at force time, unlike Icarus's continuous
            // update. A state assertion prevents static poses passing silently.
            force reference.idx=selected;
            force reference.anim=animated;force reference.af=pose;force reference.adir=direction;
            force dut.geometry.anim=animated;force dut.geometry.af=pose;force dut.geometry.adir=direction;
            // Let the unchanged blanking-latch and both memory adapters prepare.
            wait(dut.hc==0 && dut.vc==4);wait(dut.hc==0 && dut.vc==0);
            @(negedge vid);
            if(reference.idx!==selected || dut.idx!==selected || reference.anim!==animated || dut.geometry.anim!==animated ||
                reference.af!==pose || dut.geometry.af!==pose || reference.adir!==direction || dut.geometry.adir!==direction)
                $fatal(1,"requested animation/selection pose was not established");
            if(!dut.cl[1] || !reference.cl[1] || requests<20)$fatal(1,"art cache/memory model was not exercised");
            for(slot=0;slot<4;slot=slot+1)begin
                if({dut.vx[slot],dut.vs_[slot],dut.vb[slot],dut.vg[slot],dut.vv[slot],dut.vl[slot]}!==
                    {reference.vx[slot],reference.vs_[slot],reference.vb[slot],reference.vg[slot],reference.vv[slot],reference.vl[slot]})
                    $fatal(1,"latched frame parameters differ slot=%d",slot);
            end
            if(GAPS==0 || SHOWCASE)begin
                fd=$fopen($sformatf("pose-%0d.ppm",id),"wb");
                $fwrite(fd,"P6\n320 288\n255\n");
            end
            pixels=0;checking=1;
            wait(dut.vc==1);wait(dut.hc==0 && dut.vc==0);
            @(negedge vid);checking=0;
            if(fd)begin $fclose(fd);fd=0;end
            if(pixels!=320*288)$fatal(1,"wrong active pixel count %0d",pixels);
            if(fault || underrun)$fatal(1,"texture deadline failed fault=%b underrun=%b",fault,underrun);
            frames=frames+1;
            $display("frame %0d matches reference compositor, gaps=%0d bridge=%0d",id,GAPS,ASYNC_BRIDGE);
        end
    endtask
    initial begin
        force reference.count=total;force reference.idx=selected;
        force reference.menu_active=1;force reference.hold_gb=1;
        force reference.level=8;force reference.tlevel=8;
        force reference.pver=9;force reference.htw=64;force reference.hsw=0;
        force reference.anim=animated;force reference.af=pose;force reference.adir=direction;
        force dut.level=8;force dut.geometry.tlevel=8;
        force dut.geometry.anim=animated;force dut.geometry.af=pose;force dut.geometry.adir=direction;
        force reference.tag_we=ref_tag_we;force reference.tag_wa=ref_tag_addr;force reference.tag_wd=ref_tag_data;
        repeat(160)@(negedge clk);
        for(i=0;i<5;i=i+1)begin
            cache_commit=1;cache_game=i;ref_tag_we=1;ref_tag_addr=i;ref_tag_data={1'b1,11'(i)};
            force reference.tag_wa=ref_tag_addr;force reference.tag_wd=ref_tag_data;force reference.tag_we=1;
            @(negedge clk);
        end
        cache_commit=0;ref_tag_we=0;force reference.tag_we=0;
        for(i=0;i<1024;i=i+1)begin
            text_we=1;text_addr=i;text_data=SHOWCASE ? showcase_text[i] : (i<64)?16'hAA50^(16'(i)<<1):16'd0;
            #0.1;
            @(negedge clk);
        end
        text_we=0;
        repeat(200)@(negedge clk);
        if(!dut.cl[1] || !reference.cl[1])$fatal(1,"synthetic art cache initialization failed new=%b reference=%b",dut.cl[1],reference.cl[1]);
        for(i=0;i<64;i=i+1)begin
            sanity_address=i;force dut.map2_ra=sanity_address;force reference.map2_ra=sanity_address;
            repeat(4)@(negedge vid);
            if(dut.map2_q!==(SHOWCASE ? showcase_text[i]:(16'hAA50^(16'(i)<<1))) || reference.map2_q!==dut.map2_q)
                $fatal(1,"text RAM model sanity failed column=%d new=%h reference=%h",i,dut.map2_q,reference.map2_q);
        end
        release dut.map2_ra;release reference.map2_ra;
        if(SANITY_ONLY)begin $display("PASS: actual Intel RAM initialization, cache tags and full 16-bit text writes");$finish;end
        if(SHOWCASE)begin
            selected=4;one_frame(0);
            animated=1;direction=0;selected=0;
            for(i=0;i<8;i=i+1)begin pose=i;one_frame(i+1);end
            animated=0;one_frame(9);
        end else begin
            one_frame(0);
            animated=1;direction=0;pose=0;one_frame(1);
            direction=1;pose=3;one_frame(2);
            pose=7;one_frame(3);
        end
        $display("PASS: %0d full raster frames, %0d comparisons to GB/GBC with documented signed-clipping correction, variable texture latency and pixel gaps=%0d bridge=%0d",frames,comparisons,GAPS,ASYNC_BRIDGE);
        $finish;
    end
    initial begin #1000;$display("raster clock started hc=%d vc=%d",dut.hc,dut.vc);end
    initial begin #160000000;$fatal(1,"raster watchdog");end
endmodule
