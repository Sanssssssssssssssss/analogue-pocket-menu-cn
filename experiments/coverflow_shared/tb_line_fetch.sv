`timescale 1ns/1ps
module tb_line_fetch;
    reg clk=0;always #5 clk=~clk;
    reg enable=1,invalidate=0,toggle=0;
    reg [8:0] y=0;
    reg signed [10:0] x[0:3];reg [7:0] size[0:3];reg [2:0] game[0:3];reg valid[0:3],loaded[0:3];
    wire request,idle,we,underrun,fault;wire [23:0] address;wire [9:0] wa,even,odd;wire [15:0] wd;
    reg done=0;reg [31:0] data=0;
    reg respond=1,busy=0;
    reg [23:0] saved=0;
    integer latency=0,issued=0,writes=0,expected_base=8192,expected_initial=0,expected_step=256;
    reg verify=0;
    function [15:0] color(input [23:0] a);color=a[15:0]^16'hA59C;endfunction
    always @(posedge clk)begin
        done<=0;
        if(request)begin
            if(busy)$fatal(1,"second request while response outstanding");
            busy<=1;saved<=address;latency<=issued%13;issued<=issued+1;
        end
        if(busy && respond)begin
            if(latency==0)begin
                data<={color({saved[23:1],1'b1}),color({saved[23:1],1'b0})};done<=1;busy<=0;
            end else latency<=latency-1;
        end
        if(we)begin
            if(verify)begin
                if(wa[8:0]!=(expected_initial ? 0:96)+writes || wd!==color(expected_base+((expected_initial+writes*expected_step)>>8)))
                    $fatal(1,"bad texture write x=%d value=%h expected=%h base=%h step=%d initial=%d",wa[8:0],wd,color(expected_base+((expected_initial+writes*expected_step)>>8)),dut.row_base,dut.source_step,dut.initial_x);
            end else $fatal(1,"stale texture response was committed");
            writes=writes+1;
        end
    end
    coverflow_line_fetch #(.CB(3),.TIMEOUT(64)) dut(.clk(clk),.enable(enable),.invalidate(invalidate),
        .line_toggle(toggle),.line_y(y),.cover_x(x),.cover_size(size),.cover_game(game),.cover_valid(valid),.cover_loaded(loaded),
        .mem_req(request),.mem_word_addr(address),.mem_done(done),.mem_data(data),.mem_idle(idle),
        .line_we(we),.line_addr(wa),.line_data(wd),.ready_even(even),.ready_odd(odd),.underrun(underrun),.fault(fault));
    task line(input [8:0] n);
        begin @(negedge clk);y=n;toggle=~toggle;repeat(8)@(negedge clk);end
    endtask
    task clear;
        begin @(negedge clk);invalidate=1;@(negedge clk);invalidate=0;repeat(8)@(negedge clk);end
    endtask
    integer i,stage=0;
    initial begin
        for(i=0;i<4;i=i+1)begin x[i]=96;size[i]=128;game[i]=0;valid[i]=i==0;loaded[i]=1;end
        line(0);wait(even=={1'b1,9'd0});
        stage=1;
        verify=1;line(96);wait(even=={1'b1,9'd96});@(negedge clk);
        if(writes!=128 || fault || underrun)$fatal(1,"row/deadline failure");
        stage=2;
        writes=0;expected_base=126*128;line(161);wait(odd=={1'b1,9'd161});@(negedge clk);
        if(writes!=128)$fatal(1,"reflection incomplete");
        stage=3;
        verify=0;writes=0;respond=0;line(96);wait(!idle);clear;
        if(idle)$fatal(1,"invalidate released an outstanding read");
        respond=1;wait(idle);repeat(4)@(negedge clk);
        if(writes!=0 || even || odd)$fatal(1,"invalidate committed old data/readiness");
        stage=4;
        respond=0;line(96);wait(!idle);@(negedge clk);enable=0;
        repeat(8)@(negedge clk);enable=1;respond=1;wait(idle);repeat(4)@(negedge clk);
        if(writes!=0)$fatal(1,"disable/re-enable accepted stale response");
        stage=5;
        respond=0;line(96);wait(!idle);repeat(80)@(negedge clk);
        if(!fault || idle)$fatal(1,"watchdog must retain outstanding read ownership");
        respond=1;wait(idle);clear;
        if(fault || even || odd)$fatal(1,"explicit recovery failed");
        stage=6;
        verify=1;writes=0;expected_base=8192;line(0);wait(even=={1'b1,9'd0});line(96);wait(even=={1'b1,9'd96});@(negedge clk);
        if(writes!=128 || fault)$fatal(1,"recovery row failed");
        // A cropped, interpolated 74px preview must use the 80px mip, including
        // a nonzero initial source coordinate and fractional sample steps.
        verify=0;x[0]=-14;size[0]=74;line(0);wait(even=={1'b1,9'd0});
        verify=1;writes=0;expected_base=16384+8*80;expected_initial=14*276;expected_step=276;
        line(67);wait(odd=={1'b1,9'd67});@(negedge clk);
        if(writes!=60)$fatal(1,"cropped preview row incomplete");
        $display("PASS: variable latency, exact center/reflection samples, invalidate and disable with pending reads, watchdog ownership, explicit recovery");$finish;
    end
    initial begin #1000000;$fatal(1,"transport watchdog stage=%d state=%d y=%d even=%h pending=%b fault=%b which=%d x=%d end=%d",stage,dut.state,dut.y,even,dut.pending,fault,dut.which,dut.screen_x,dut.end_x);end
endmodule
