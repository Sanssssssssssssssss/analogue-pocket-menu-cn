`timescale 1ns/1ps
// Only datatable RAM storage is stubbed; command/semaphore and CDC use actual RTL.
module mf_datatable(input [9:0] address_a,address_b,input clock_a,clock_b,
    input [31:0] data_a,data_b,input wren_a,wren_b,output [31:0] q_a,q_b);
    assign q_a=0;assign q_b=0;
endmodule
module tb_commands;
    reg clk=0;always #7 clk=~clk;
    reg rd=0,wr=0,op=0,flush=0,bw=0,br=0;
    reg [31:0] ba=0,bd=0;wire [31:0] q;wire done,ack;wire [2:0] error;
    reg [15:0] slot=100;
    core_bridge_cmd dut (
        .clk(clk),.bridge_endian_little(1'b0),.bridge_addr(ba),.bridge_rd(br),.bridge_wr(bw),.bridge_wr_data(bd),.bridge_rd_data(q),
        .status_boot_done(1'b1),.status_setup_done(1'b0),.status_running(1'b1),
        .dataslot_requestread_ack(1'b0),.dataslot_requestread_ok(1'b0),.dataslot_requestwrite_ack(1'b0),.dataslot_requestwrite_ok(1'b0),
        .savestate_supported(1'b0),.savestate_addr(32'd0),.savestate_size(32'd0),.savestate_maxloadsize(32'd0),
        .savestate_start_ack(1'b0),.savestate_start_busy(1'b0),.savestate_start_ok(1'b0),.savestate_start_err(1'b0),
        .savestate_load_ack(1'b0),.savestate_load_busy(1'b0),.savestate_load_ok(1'b0),.savestate_load_err(1'b0),
        .target_dataslot_read(rd),.target_dataslot_write(wr),.target_dataslot_getfile(1'b0),.target_dataslot_openfile(op),.target_dataslot_flush(flush),
        .target_dataslot_ack(ack),.target_dataslot_done(done),.target_dataslot_err(error),.target_dataslot_id(slot),
        .target_dataslot_slotoffset(32'h1234),.target_dataslot_bridgeaddr(32'h20000000),.target_dataslot_length(32'h10000),
        .target_buffer_param_struct(32'hF3000000),.target_buffer_resp_struct(32'd0),
        .datatable_addr(10'd0),.datatable_wren(1'b0),.datatable_data(32'd0));
    task host(input [31:0] value);
        begin @(negedge clk);ba=32'hF8001000;bd=value;bw=1;@(negedge clk);bw=0;repeat(3)@(negedge clk);end
    endtask
    task operation(input [15:0] code,input [2:0] result);
        begin
            @(negedge clk);rd=code==16'h180;wr=code==16'h184;flush=code==16'h188;op=code==16'h192;
            @(negedge clk);rd=0;wr=0;flush=0;op=0;
            wait(dut.target_0[31:16]==16'h636d && dut.target_0[15:0]==code);
            if(done || dut.target_20!=slot)$fatal(1,"command not armed or wrong slot");
            if(code==16'h192 && dut.target_24!=32'hF3000000)$fatal(1,"wrong filename pointer");
            if(code==16'h180 && (dut.target_24!=32'h1234||dut.target_28!=32'h20000000||dut.target_2C!=32'h10000))$fatal(1,"read params");
            host({16'h6275,code});wait(ack);if(done)$fatal(1,"busy treated as done");
            host({16'h6f6b,13'd0,result});wait(done);
            if(error!==result)$fatal(1,"lost APF error result");repeat(8)@(negedge clk);
        end
    endtask
    initial begin
        // Cyclone V power-up initializes these uninitialized upstream state registers to 0.
        dut.tstate=0;dut.hstate=0;dut.target_0=0;
        repeat(12)@(negedge clk);
        operation(16'h192,1);operation(16'h180,0);slot=10;operation(16'h184,0);
        operation(16'h188,4);operation(16'h188,0);slot=11;operation(16'h188,0);
        $display("PASS: actual core_bridge_cmd open/read/write/flush semaphore, slot parameters, busy/done and error propagation");$finish;
    end
    initial begin #100000;$fatal(1,"command watchdog");end
endmodule
