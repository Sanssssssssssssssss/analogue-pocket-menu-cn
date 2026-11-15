`timescale 1ns/1ps
module tb_target;
    reg clk=0;always #7 clk=~clk;
    reg little=0,wr=0,rd=0,setup=0;
    reg [31:0] bus_address=0,bus_data=0;
    wire [31:0] bus_read_data;
    wire running;
    reg read_request=0,write_request=0,open_request=0,flush_request=0;
    reg [15:0] slot=0;
    reg [31:0] offset=0,address=0,length=0;
    wire complete,raw_request,raw_ack,raw_done;
    wire [2:0] error;
    wire [15:0] raw_command,raw_result;
    wire [31:0] p0,p1,p2,p3;
    integer boot_messages=0,operations=0,n,order;
    sega_menu_target adapter(.clk(clk),.ready(running),.read_request(read_request),.write_request(write_request),
        .open_request(open_request),.flush_request(flush_request),.slot(slot),.offset(offset),.address(address),.length(length),
        .complete(complete),.error(error),.raw_request(raw_request),.raw_command(raw_command),.p0(p0),.p1(p1),.p2(p2),.p3(p3),
        .raw_ack(raw_ack),.raw_done(raw_done),.raw_result(raw_result));
    core_bridge_cmd bridge(.clk(clk),.reset_n(running),.bridge_endian_little(little),.bridge_addr(bus_address),
        .bridge_rd(rd),.bridge_rd_data(bus_read_data),.bridge_wr(wr),.bridge_wr_data(bus_data),
        .status_boot_done(1'b1),.status_setup_done(setup),.status_running(running),
        .dataslot_requestread_ack(1'b1),.dataslot_requestread_ok(1'b1),.dataslot_requestwrite_ack(1'b1),.dataslot_requestwrite_ok(1'b1),
        .savestate_supported(1'b0),.savestate_addr(32'd0),.savestate_size(32'd0),.savestate_maxloadsize(32'd0),
        .savestate_start_ack(1'b0),.savestate_start_busy(1'b0),.savestate_start_ok(1'b0),.savestate_start_err(1'b1),
        .savestate_load_ack(1'b0),.savestate_load_busy(1'b0),.savestate_load_ok(1'b0),.savestate_load_err(1'b1),
        .target_cmd_req(raw_request),.target_cmd(raw_command),.target_cmd_p0(p0),.target_cmd_p1(p1),.target_cmd_p2(p2),.target_cmd_p3(p3),
        .target_cmd_ack(raw_ack),.target_cmd_done(raw_done),.target_cmd_result(raw_result),
        .datatable_addr(10'd0),.datatable_wren(1'b0),.datatable_data(32'd0));
    function [31:0] swapped(input [31:0] value);
        swapped={value[7:0],value[15:8],value[23:16],value[31:24]};
    endfunction
    task bus_write(input [31:0] at,input [31:0] value);
        begin @(negedge clk);bus_address=at;bus_data=little ? swapped(value):value;wr=1;
            @(negedge clk);wr=0;repeat(3)@(negedge clk);end
    endtask
    task bus_read(input [31:0] at,output [31:0] value);
        begin @(negedge clk);bus_address=at;rd=1;repeat(3)@(negedge clk);
            value=little ? swapped(bus_read_data):bus_read_data;rd=0;@(negedge clk);end
    endtask
    task request_ui(input integer kind);
        begin
            @(negedge clk);slot=16'd100;offset=32'h1234;address=32'h71000000;length=2048;
            read_request=kind==0;write_request=kind==1;open_request=kind==2;flush_request=kind==3;
            @(negedge clk);read_request=0;write_request=0;open_request=0;flush_request=0;
            // The interface must capture the original operation, not these.
            slot=9;offset=0;address=0;length=0;
        end
    endtask
    task admitted(input [15:0] command,input integer kind);
        reg [31:0] value;
        integer tries;
        begin
            tries=0;value=0;
            while(value!={16'h636d,command})begin
                bus_read(32'hF8001000,value);tries=tries+1;
                if(value==32'h636d0140)begin
                    boot_messages=boot_messages+1;bus_write(32'hF8001000,32'h6f6b0000);value=0;
                end
                if(tries>200)$fatal(1,"target command was lost cmd=%h actual=%h",command,value);
            end
            bus_read(32'hF8001020,value);if(value!=100)$fatal(1,"slot parameter changed");
            bus_read(32'hF8001024,value);if(value!=(kind==2 ? 32'hF3000000:kind==3 ? 0:32'h1234))$fatal(1,"offset/struct parameter changed");
            bus_read(32'hF8001028,value);if(value!=(kind>=2 ? 0:32'h71000000))$fatal(1,"address parameter changed");
            bus_read(32'hF800102c,value);if(value!=(kind>=2 ? 0:2048))$fatal(1,"length parameter changed");
            if(complete)$fatal(1,"completion accepted before actual host response");
            operations=operations+1;
        end
    endtask
    task finish(input [15:0] result);
        begin
            repeat(17)begin @(negedge clk);if(complete)$fatal(1,"stale completion");end
            bus_write(32'hF8001000,{16'h6f6b,result});wait(complete);repeat(2)@(negedge clk);
            if(error!=(result>7 ? 3'd7:result[2:0]))$fatal(1,"result code truncated unsafely");
        end
    endtask
    initial begin
        repeat(16)@(negedge clk);
        bus_write(32'hF8000000,32'h434d0011);wait(running);
        // Ready-to-Run races admission. The request must survive its priority.
        @(negedge clk);setup=1;request_ui(0);admitted(16'h0180,0);finish(0);
        if(boot_messages!=1)$fatal(1,"boot handshake missing or duplicated");
        for(order=0;order<2;order=order+1)begin
            little=order;repeat(10)@(negedge clk);
            request_ui(0);admitted(16'h0180,0);finish(0);
            request_ui(1);admitted(16'h0184,1);finish(0);
            request_ui(2);admitted(16'h0192,2);finish(3);
            request_ui(3);admitted(16'h0188,3);finish(16'hffff);
        end
        // Stop with an admitted command; its completion arrives while stopped.
        request_ui(0);admitted(16'h0180,0);
        bus_write(32'hF8000000,32'h434d0010);wait(!running);repeat(6)@(negedge clk);
        if(!complete || raw_request || bridge.tstate!=0)$fatal(1,"Stop left an operation owning the bridge");
        bus_write(32'hF8001000,32'h6f6b0000);repeat(5)@(negedge clk);
        if(raw_done)$fatal(1,"unowned late completion published");
        bus_write(32'hF8000000,32'h434d0011);wait(running);
        request_ui(2);admitted(16'h0192,2);finish(0);
        $display("PASS: %0d actual bridge operations, boot priority, both byte orders, read/write/open/flush parameters, error clamp, Stop/Run and unowned late response",operations);$finish;
    end
    initial begin #1000000;$fatal(1,"target protocol watchdog");end
endmodule

// This test never accesses the slot table. Replace its unrelated RAM with a
// constant stub; the actual command executor, synchronizer and adapter run.
module mf_datatable(input [9:0] address_a,address_b,input clock_a,clock_b,
    input [31:0] data_a,data_b,input wren_a,wren_b,output [31:0] q_a,q_b);
    assign q_a=0;assign q_b=0;
endmodule
