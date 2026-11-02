`timescale 1ns/1ps
// Real APF engine, generated menu wiring, Intel loaders/RAM and pin-level
// CellRAM. Game CPU and native ready/idle inputs are outside this probe.
module tb_coverflow_boot;
    reg clk_74a=0,clk_vid=0,clk_sys=0;
    always #6.734 clk_74a=~clk_74a;
    always #59.604644775390625 clk_vid=~clk_vid;
    always #4.967053731282552 clk_sys=~clk_sys;
    reg booted=0,bridge_wr=0,bridge_rd=0;
    reg [31:0] bridge_addr=0,bridge_wr_data=0,cont1_key=0;
    wire bridge_endian_little=1'b0,pll_core_locked_s=1'b1;
    wire reset_n;
    wire ui_owned,ui_show,ui_reset,ui_pause,ui_new_load,ui_finish,ui_bound,ui_fault;
    wire [7:0] ui_fault_code,ui_first_fault_code,ui_state;
    wire [10:0] ui_selected;
    wire [31:0] ui_param_data;
    wire [31:0] ui_capacity=32'd65536;
    wire ui_frame_request,ui_flush;
    wire ui_frame_ack_b=0,ui_frame_started_b=0,ui_frame_valid_b=0,ui_frame_fault_b=0;
    wire ui_visible_bridge=0,ui_prepare_ready_b=1,ui_load_ready_b=1,ui_io_idle_b=1;
    wire cf_game_vs=0; // A reset GBA cannot supply frame ticks to the menu.
    wire target_dataslot_read,target_dataslot_write,target_dataslot_openfile,target_dataslot_done;
    wire [2:0] target_dataslot_err;
    wire [15:0] target_dataslot_id;
    wire [31:0] target_dataslot_slotoffset,target_dataslot_bridgeaddr,target_dataslot_length;
    wire [21:16] cram1_a;
    wire [15:0] cram1_dq;
    wire cram1_wait=0;
    wire cram1_clk,cram1_adv_n,cram1_cre,cram1_ce0_n,cram1_ce1_n;
    wire cram1_oe_n,cram1_we_n,cram1_ub_n,cram1_lb_n;
    /* GENERATED_UI_WIRING */
    wire [31:0] command_data;
    core_bridge_cmd commands(
        .clk(clk_74a),.bridge_endian_little(bridge_endian_little),.bridge_addr(bridge_addr),
        .bridge_rd(bridge_rd),.bridge_wr(bridge_wr),.bridge_wr_data(bridge_wr_data),
        .bridge_rd_data(command_data),.reset_n(reset_n),
        .status_boot_done(booted),.status_setup_done(booted),.status_running(reset_n),
        .dataslot_requestread_ack(1'b1),.dataslot_requestread_ok(1'b1),
        .dataslot_requestwrite_ack(1'b1),.dataslot_requestwrite_ok(1'b1),
        .savestate_supported(1'b0),.savestate_addr(32'd0),.savestate_size(32'd0),.savestate_maxloadsize(32'd0),
        .savestate_start_ack(1'b1),.savestate_start_busy(1'b0),.savestate_start_ok(1'b0),.savestate_start_err(1'b1),
        .savestate_load_ack(1'b1),.savestate_load_busy(1'b0),.savestate_load_ok(1'b0),.savestate_load_err(1'b1),
        .target_dataslot_read(target_dataslot_read),.target_dataslot_write(target_dataslot_write),
        .target_dataslot_getfile(1'b0),.target_dataslot_openfile(target_dataslot_openfile),.target_dataslot_flush(ui_flush),
        .target_dataslot_id(target_dataslot_id),.target_dataslot_slotoffset(target_dataslot_slotoffset),
        .target_dataslot_bridgeaddr(target_dataslot_bridgeaddr),.target_dataslot_length(target_dataslot_length),
        .target_dataslot_ack(),.target_dataslot_done(target_dataslot_done),.target_dataslot_err(target_dataslot_err),
        .target_buffer_param_struct(32'hF3000000),.target_buffer_resp_struct(32'd0),
        .datatable_addr(10'd0),.datatable_wren(1'b0),.datatable_data(32'd0));
    integer physical_reads,physical_writes;
    sim_cellram physical_memory(.a(cram1_a),.dq(cram1_dq),.clk(cram1_clk),.adv_n(cram1_adv_n),.cre(cram1_cre),
        .ce0_n(cram1_ce0_n),.ce1_n(cram1_ce1_n),.oe_n(cram1_oe_n),.we_n(cram1_we_n),.ub_n(cram1_ub_n),.lb_n(cram1_lb_n),
        .reads(physical_reads),.writes(physical_writes));
    reg [7:0] page[0:1000000];
    initial $readmemh("page.hex",page);
    task write_word(input [31:0] at,input [31:0] value);
        begin
            @(negedge clk_74a);bridge_addr=at;bridge_wr_data=value;bridge_wr=1;
            @(negedge clk_74a);bridge_wr=0;repeat(74)@(negedge clk_74a);
        end
    endtask
    task host_command(input [15:0] code);
        begin write_word(32'hF8000000,{16'h434d,code});wait(commands.host_0[31:16]==16'h4f4b);
            if(commands.host_0[15:0]!=0)$fatal(1,"host command failed %h",code);end
    endtask
    integer offset,size,at,operations=0,art_chunks=0,text_words=0;
    reg [31:0] destination,word;
    initial begin
        commands.tstate=0;commands.hstate=0;commands.target_0=0;commands.host_0=0;commands.host_cmd_start=0;
        commands.status_setup_done_1=0;
        commands.target_dataslot_read_1=0;commands.target_dataslot_write_1=0;
        commands.target_dataslot_getfile_1=0;commands.target_dataslot_openfile_1=0;
        #100;booted=1;
        host_command(16'h8f);
        wait(commands.target_0==32'h636d0140);write_word(32'hf8001000,32'h6f6b0000);
        host_command(16'h11);
        forever begin
            wait(commands.target_0[31:16]==16'h636d);
            if(commands.target_0[15:0]!=16'h180 || commands.target_20!=100)
                $fatal(1,"unexpected menu command %h",commands.target_0);
            offset=commands.target_24;destination=commands.target_28;size=commands.target_2C;
            if(size>16384 || size<4 || size%4)$fatal(1,"unbounded read");
            if(destination[31:28]==4)art_chunks=art_chunks+1;
            else if(destination==32'h71000000)text_words=text_words+size/4;
            else if(destination[31:28]!=6 && destination[31:28]!=7)$fatal(1,"cover traffic reached game/save bus");
            write_word(32'hf8001000,32'h62750180);
            for(at=0;at<size;at=at+4)begin
                word={page[offset+at],page[offset+at+1],page[offset+at+2],page[offset+at+3]};
                write_word(destination+at,word);
            end
            write_word(32'hf8001000,32'h6f6b0000);operations=operations+1;
            repeat(100)@(negedge clk_74a);
        end
    end
    integer frame_pixels=0,frames=0,poses=0;
    reg previous_vs=0,previous_hs=0,previous_de=0;
    always @(posedge clk_vid)begin
        #0.1;
        if(cf_vs && previous_vs || cf_hs && previous_hs)$fatal(1,"stretched physical sync pulse");
        if(cf_skip && !cf_de)$fatal(1,"scaler skip outside active pixels");
        if(cf_de && !cf_skip)frame_pixels=frame_pixels+1;
        if(cf_vs)begin
            if(frames>0 && frame_pixels!=92160)$fatal(1,"incomplete raster %d",frame_pixels);
            frame_pixels=0;frames=frames+1;
            $display("frame=%d level=%d state=%d uploaded_halfwords=%d",frames,cf_level,ui_state,physical_writes);
        end
        previous_vs=cf_vs;previous_hs=cf_hs;previous_de=cf_de;
    end
    always @(posedge clk_74a)begin
        if(ui_fault || cf_fetch_fault || cf_underrun)
            $fatal(1,"UI fault state=%d error=%h art=%b view=%b underrun=%b",ui_state,ui_fault_code,cf_art_fault,cf_view_fault,cf_underrun);
        // upload_ready includes read-idle and may drop during an unrelated
        // raster read after the controller observed its synchronized value.
        if(cf_commit && (cf_images.received!=22784 || cf_images.uploading || cf_images.used!=0 || physical_writes%22784!=0))
            $fatal(1,"unwritten cover published");
        if(cf_tick && cf_anim)poses=poses | (1<<cf_view.af);
    end
    initial begin
        wait(ui_state==13 && cf_level!=0 && physical_writes==45568);
        wait(cf_tick);wait(!cf_tick);wait(cf_tick);
        if(!ui_reset || ui_bound || !ui_owned || art_chunks!=6 || text_words!=512 || physical_reads<1000)
            $fatal(1,"cold boot did not exercise full F2/CellRAM/menu path");
        @(negedge clk_74a);cont1_key=32'h2;
        repeat(4)@(negedge clk_74a);cont1_key=0;
        wait(cf_anim);
        if($test$plusargs("full_animation"))begin
            wait(!cf_anim);wait(cf_title_level==8);
            if(poses!=255)$fatal(1,"eight key-driven animation poses incomplete %h",poses);
        end
        if(ui_selected!=1 || !ui_reset || ui_bound || frames<2)
            $fatal(1,"key-driven CoverFlow animation did not start selection=%d frames=%d",ui_selected,frames);
        $display("PASS: real APF cold boot, two complete CellRAM covers without duplicate reads, Intel FIFO/RAM, held-reset game VS=0, full GBA-clock raster and key-triggered CoverFlow; operations=%d reads=%d writes=%d",operations,physical_reads,physical_writes);
        $finish;
    end
    initial begin #600000000;$fatal(1,"cold boot watchdog state=%d first=%h level=%d target=%h",ui_state,ui_first_fault_code,cf_level,commands.target_0);end
endmodule
