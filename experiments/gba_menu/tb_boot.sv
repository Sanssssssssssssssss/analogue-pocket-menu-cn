`timescale 1ns/1ps
// Actual menu + command engine + pixel FIFO + raster. No GBA CPU or physical RAM.
module tb_boot;
    reg clk=0,memory=0,video=0;
    always #6.734 clk=~clk;
    always #4.967 memory=~memory;
    always #59.605 video=~video;
    reg booted=0,reset=1;
    reg [31:0] addr=0,data=0;
    reg wr=0,rd=0;
    wire reset_n;
    wire t_read,t_write,t_open,t_flush,t_done,t_ack;
    wire [2:0] t_error;wire [15:0] slot;
    wire [31:0] offset,address,length,param,cmd_data;
    wire request,owned,show,menu_reset,pause,finish,new_load,bound,fault;
    wire [7:0] state,code;wire [10:0] selected;
    wire ack,started,valid,frame_fault,visible,game_ready;
    wire [15:0] pa,received,words;wire [17:0] pd;wire we;
    wire [23:0] rgb;wire de,vs,hs,skip;
    gba_menu #(.TIMEOUT(34'd7425000),.FRAME_TIMEOUT(34'd742500)) menu(
        .clk(clk),.ready(reset_n),.buttons(32'd0),.bridge_wr(wr),.bridge_rd(rd),
        .bridge_endian_little(1'b0),.bridge_addr(addr),.bridge_wr_data(data),.param_rd_data(param),
        .t_read(t_read),.t_write(t_write),.t_open(t_open),.t_flush(t_flush),.t_slot(slot),.t_offset(offset),.t_address(address),.t_length(length),.t_done(t_done),.t_error(t_error),
        .frame_ack(ack),.frame_started(started),.frame_valid(valid),.frame_fault(frame_fault),.visible(visible),
        .prepare_ready(1'b1),.load_ready(1'b1),.io_idle(1'b1),.save_capacity(32'd65536),
        .frame_request(request),.menu_owned(owned),.menu_show(show),.menu_reset(menu_reset),.menu_pause(pause),.new_load(new_load),.finish_load(finish),.game_bound(bound),.fault(fault),.fault_code(code),.state(state),.selected(selected));
    core_bridge_cmd commands(
        .clk(clk),.bridge_endian_little(1'b0),.bridge_addr(addr),.bridge_rd(rd),.bridge_wr(wr),.bridge_wr_data(data),.bridge_rd_data(cmd_data),.reset_n(reset_n),
        .status_boot_done(booted),.status_setup_done(booted),.status_running(reset_n),
        .dataslot_requestread_ack(1'b1),.dataslot_requestread_ok(1'b1),.dataslot_requestwrite_ack(1'b1),.dataslot_requestwrite_ok(1'b1),
        .savestate_supported(1'b0),.savestate_addr(32'd0),.savestate_size(32'd0),.savestate_maxloadsize(32'd0),
        .savestate_start_ack(1'b1),.savestate_start_busy(1'b0),.savestate_start_ok(1'b0),.savestate_start_err(1'b1),
        .savestate_load_ack(1'b1),.savestate_load_busy(1'b0),.savestate_load_ok(1'b0),.savestate_load_err(1'b1),
        .target_dataslot_read(t_read),.target_dataslot_write(t_write),.target_dataslot_getfile(1'b0),.target_dataslot_openfile(t_open),.target_dataslot_flush(t_flush),
        .target_dataslot_id(slot),.target_dataslot_slotoffset(offset),.target_dataslot_bridgeaddr(address),.target_dataslot_length(length),
        .target_dataslot_ack(t_ack),.target_dataslot_done(t_done),.target_dataslot_err(t_error),
        .target_buffer_param_struct(32'hF3000000),.target_buffer_resp_struct(32'd0),
        .datatable_addr(10'd0),.datatable_wren(1'b0),.datatable_data(32'd0));
    gba_menu_pixels pixels(
        .clk_bridge(clk),.clk_memory(memory),.bridge_wr(wr),.bridge_endian_little(1'b0),.bridge_addr(addr),.bridge_wr_data(data),
        .menu_owned(owned),.frame_request(request),.game_pixel_addr(16'd0),.game_pixel_we(1'b0),
        .pixel_addr(pa),.pixel_data(pd),.pixel_we(we),.frame_ack(ack),.frame_started(started),.frame_valid(valid),.frame_fault(frame_fault),.game_frame_ready(game_ready),
        .received_pixels(received),.bridge_words(words));
    video_adapter display(.clk_sys(memory),.clk_vid(video),.menu_show(show),.menu_fault(fault),.menu_visible(visible),.reset(reset),
        .pixel_addr(pa),.pixel_data(pd),.pixel_we(we),.video_rgb(rgb),.video_de(de),.video_vs(vs),.video_hs(hs),.video_skip(skip));
    reg [7:0] page[0:1000000];initial $readmemh("page.hex",page);
    task write_word(input [31:0] a,input [31:0] d);
        begin @(negedge clk);addr=a;data=d;wr=1;@(negedge clk);wr=0;repeat(88)@(negedge clk);end
    endtask
    task host_command(input [15:0] c);
        begin write_word(32'hF8000000,{16'h434d,c});wait(commands.host_0[31:16]==16'h4f4b);
            if(commands.host_0[15:0]!=0)$fatal(1,"host command %h failed",c);end
    endtask
    integer i,at,source,size,operations=0,chunks=0,frame_base;
    reg [31:0] destination,word;
    reg [15:0] expected_pixel;
    initial if($test$plusargs("dirty_boot"))begin
        #20;menu.menu_owned=0;menu.menu_reset=0;menu.game_bound=1;
    end
    initial begin
        commands.tstate=0;commands.hstate=0;commands.target_0=0;commands.host_0=0;commands.host_cmd_start=0;
        commands.status_setup_done_1=0;
        commands.target_dataslot_read_1=0;commands.target_dataslot_write_1=0;commands.target_dataslot_getfile_1=0;commands.target_dataslot_openfile_1=0;
        #100;booted=1;reset=0;
        host_command(16'h8f);
        wait(commands.target_0==32'h636d0140);write_word(32'hf8001000,32'h6f6b0000);
        host_command(16'h11);
        repeat(4)@(negedge clk);
        if(!owned || !menu_reset || bound)$fatal(1,"boot did not acquire framebuffer/reset game ownership");
        while(operations<7)begin
            wait(commands.target_0[31:16]==16'h636d);
            if(commands.target_0[15:0]!=16'h180 || commands.target_20!=100)$fatal(1,"unexpected menu command %h",commands.target_0);
            source=commands.target_24;destination=commands.target_28;size=commands.target_2C;
            if(size>16384)$fatal(1,"oversized menu read");
            if(destination[31:28]==5)chunks=chunks+1;
            write_word(32'hf8001000,32'h62750180);
            for(at=0;at<size;at=at+4)begin
                word={page[source+at],page[source+at+1],page[source+at+2],page[source+at+3]};
                if(!($test$plusargs("drop_last") && destination+at==32'h50012bfc))write_word(destination+at,word);
            end
            write_word(32'hf8001000,32'h6f6b0000);operations=operations+1;
            repeat(100)@(negedge clk);
        end
        wait(state==13 || fault);
        if($test$plusargs("drop_last"))begin
            if(!fault || code!=8'h22 || received!=38398 || words!=19199 || bound)$fatal(1,"incomplete frame was not rejected");
            wait(visible && de && rgb!=0);
            $display("PASS: host success with missing final pixels becomes a visible error instead of a black wait");$finish;
        end
        if(fault || chunks!=5 || words!=19200 || received!=38400 || !owned || !menu_reset || bound)$fatal(1,"startup state=%0d error=%h chunks=%0d words=%0d pixels=%0d owned=%b",state,code,chunks,words,received,owned);
        frame_base={page[15],page[14],page[13],page[12]};
        for(i=0;i<38400;i=i+1)begin
            expected_pixel={page[frame_base+2*i+1],page[frame_base+2*i]};
            if(display.framebuffer[i]!=={expected_pixel[15:11],expected_pixel[15],expected_pixel[10:5],expected_pixel[4:0],expected_pixel[4]})$fatal(1,"framebuffer mismatch %0d",i);
        end
        wait(visible && de && rgb!=0);
        $display("PASS: real APF command startup + menu metadata + five frame chunks + Intel FIFO + visible first raster; words=19200 pixels=38400");$finish;
    end
    initial begin #100000000;$fatal(1,"startup watchdog state=%0d error=%h target=%h words=%0d pixels=%0d",state,code,commands.target_0,words,received);end
endmodule
