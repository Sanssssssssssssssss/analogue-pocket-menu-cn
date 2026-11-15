// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module mf_datatable(input [9:0] address_a,address_b,input clock_a,clock_b,
    input [31:0] data_a,data_b,input wren_a,wren_b,output [31:0] q_a,q_b);
    assign q_a=0; assign q_b=0;
endmodule
module tb_runtime;
    reg clk=0; always #5 clk=~clk;
    reg power_reset=1,run=0,menu=0,write=0,bw=0;
    reg [15:0] keys=16'h10;
    reg [31:0] address=0,value=0,ba=0,bd=0;
    wire [31:0] data,q; wire rd,op,ack,done; wire [2:0] error;
    integer requests=0,i;
    reg [287:0] path;
    runtime_request probe(clk,power_reset,run,menu,keys,address,value,write,ack,done,error,rd,op,data);
    always @(posedge clk) if(rd||op) begin
        requests<=requests+1;
        if(rd&&op)$fatal(1,"two file commands");
        if(!run||menu)$fatal(1,"request outside normal runtime");
    end
    core_bridge_cmd sdk(
        .clk(clk),.bridge_endian_little(1'b0),.bridge_addr(ba),.bridge_rd(1'b0),
        .bridge_wr(bw),.bridge_wr_data(bd),.bridge_rd_data(q),
        .status_boot_done(1'b1),.status_setup_done(1'b0),.status_running(1'b1),
        .dataslot_requestread_ack(1'b0),.dataslot_requestread_ok(1'b0),
        .dataslot_requestwrite_ack(1'b0),.dataslot_requestwrite_ok(1'b0),
        .savestate_supported(1'b0),.savestate_addr(32'd0),.savestate_size(32'd0),.savestate_maxloadsize(32'd0),
        .savestate_start_ack(1'b0),.savestate_start_busy(1'b0),.savestate_start_ok(1'b0),.savestate_start_err(1'b0),
        .savestate_load_ack(1'b0),.savestate_load_busy(1'b0),.savestate_load_ok(1'b0),.savestate_load_err(1'b0),
        .target_dataslot_read(rd),.target_dataslot_write(1'b0),.target_dataslot_getfile(1'b0),.target_dataslot_openfile(op),
        .target_dataslot_ack(ack),.target_dataslot_done(done),.target_dataslot_err(error),
        .target_dataslot_id(16'd0),.target_dataslot_slotoffset(32'd0),
        .target_dataslot_bridgeaddr(32'h60000080),.target_dataslot_length(32'd16),
        .target_buffer_param_struct(32'hF3000000),.target_buffer_resp_struct(32'd0),
        .datatable_addr(10'd0),.datatable_wren(1'b0),.datatable_data(32'd0));
    task tick;begin repeat(8)@(negedge clk);end endtask
    task put(input [31:0] addr,input [31:0] val);
        begin @(negedge clk);address=addr;value=val;write=1;@(negedge clk);write=0;tick;end
    endtask
    task expect_data(input [31:0] addr,input [31:0] val);
        begin address=addr;#1;if(data!==val)$fatal(1,"read %h got %h expected %h",addr,data,val);end
    endtask
    task host(input [31:0] val);
        begin @(negedge clk);ba=32'hF8001000;bd=val;bw=1;@(negedge clk);bw=0;tick;end
    endtask
    task complete(input [15:0] code,input [2:0] result);
        begin
            wait(sdk.target_0=={16'h636D,code});tick;
            if(sdk.target_20!=0)$fatal(1,"wrong slot");
            if(code==16'h180 && (sdk.target_24!=0||sdk.target_28!=32'h60000080||sdk.target_2C!=16))$fatal(1,"read bounds");
            if(code==16'h192 && sdk.target_24!=32'hF3000000)$fatal(1,"open pointer");
            expect_data(32'h600000B0,code==16'h180 ? 32'h10003 : 32'h20003);
            host({16'h6275,code});
            expect_data(32'h600000B0,code==16'h180 ? 32'h10007 : 32'h20007);
            host({16'h6F6B,13'd0,result});
            expect_data(32'h600000B0,(code==16'h180 ? 32'h1000F : 32'h2000F)|({29'd0,result}<<8));
        end
    endtask
    initial begin
        sdk.tstate=0;sdk.hstate=0;sdk.target_0=0;sdk.host_0=0;sdk.host_cmd_start=0;
        sdk.status_setup_done_1=0;sdk.target_dataslot_read_1=0;sdk.target_dataslot_write_1=0;
        sdk.target_dataslot_getfile_1=0;sdk.target_dataslot_openfile_1=0;
        tick;power_reset=0;tick;
        // Check the entire constant open struct, including padding/flags/size.
        path=0;
        for(i=0;i<9;i=i+1)begin address=32'hF3000000+i*4;#1;path={path[255:0],data};end
        if(path!=={"/Assets/routetest/common/probe.dat",16'd0})$fatal(1,"filename bytes");
        for(i=9;i<66;i=i+1)begin address=32'hF3000000+i*4;#1;if(data!==0)$fatal(1,"padding or nonzero open flags/size");end
        put(32'h60000030,1);run=1;tick;
        if(requests!=0)$fatal(1,"held Run accepted");
        run=0;keys=0;tick;keys=16'h20;tick;
        run=1;menu=1;keys=0;tick;keys=16'h20;tick;menu=0;tick;
        if(requests!=0)$fatal(1,"menu/reset input accepted");
        keys=0;tick;keys=16'h30;tick;if(requests!=0)$fatal(1,"ambiguous keys");
        keys=0;tick;keys=16'h20;tick;
        complete(16'h180,0);expect_data(32'h60000034,2);
        keys=0;tick;keys=16'h10;tick;
        if(requests!=1)$fatal(1,"request repeated");
        put(32'h600000B0,0);expect_data(32'h600000B0,32'h1000F);
        put(32'h600000B4,0);expect_data(32'h600000B4,1);
        put(32'h600000B8,0);expect_data(32'h600000B8,2);
        // SDK done is still high here: it must not complete the next operation.
        put(32'h60000030,2);tick;expect_data(32'h600000B0,32'h20001);
        keys=0;tick;keys=16'h10;tick;
        complete(16'h192,3);expect_data(32'h60000034,1);
        if(requests!=2)$fatal(1,"wrong request count");
        put(32'h60000030,3);keys=0;tick;keys=16'h20;tick;
        if(requests!=2)$fatal(1,"invalid mode armed");
        $display("PASS: runtime release/menu/reset guards, one-shot 0180/0192, actual SDK busy/done/error, stale-done rejection, immutable readouts and read-only open struct");
        $finish;
    end
    initial begin #100000;$fatal(1,"runtime watchdog");end
endmodule
