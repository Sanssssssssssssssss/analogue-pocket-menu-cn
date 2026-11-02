`timescale 1ns/1ps
// Synthetic asynchronous CellRAM pin model. Timing bounds follow the pinned
// driver's defaults (70 ns access/write, 45 ns WE, 20 ns data setup). This is
// not a vendor device model and does not certify the physical board.
module sim_cellram (
    input wire [21:16] a,
    inout wire [15:0] dq,
    input wire clk,adv_n,cre,ce0_n,ce1_n,oe_n,we_n,ub_n,lb_n,
    output integer reads=0,writes=0
);
    // A sparse but nonaliasing model for the six slots used by these tests.
    reg [15:0] words[0:196607];
    reg written[0:196607];
    reg [21:0] address=0;
    reg active=0,writing=0,valid=0;
    reg [15:0] value=0,last_write_data=0;
    realtime started=0,last_data_time=0,adv_ended=0;
    integer i,index;
    initial for(i=0;i<196608;i=i+1)written[i]=0;
    function integer packed_address(input [21:0] raw);
        integer slot;
        begin
            slot=raw[21:15];
            if(slot==127)slot=5;
            else if(slot>4)$fatal(1,"test model unsupported physical slot %d",slot);
            packed_address=slot*32768+raw[14:0];
        end
    endfunction
    assign dq=(!ce0_n && ce1_n && !oe_n && we_n && valid) ? value:16'hzzzz;
    always @(negedge adv_n)begin
        #0.001;
        if(active || ce0_n || !ce1_n || cre || clk || ub_n || lb_n)$fatal(1,"unsafe CellRAM address admission");
        started=$realtime;active=1;writing=!we_n;valid=0;
    end
    always @(posedge adv_n)if(active)begin
        if($realtime-started<7 || (^dq)===1'bx)$fatal(1,"CellRAM address setup/CE timing");
        address={a,dq};adv_ended=$realtime;
        if(!writing)begin
            if($realtime-started<70)#(70-($realtime-started));
            index=packed_address(address);
            if(!written[index])$fatal(1,"read before CellRAM upload addr=%h",address);
            value=words[index];valid=1;reads=reads+1;
        end
    end
    always @(negedge oe_n)if(active && !writing)
        if($realtime-adv_ended<2 || !we_n)$fatal(1,"CellRAM address hold/OE timing");
    always @(dq)if(active && writing && !we_n && adv_n && (^dq)!==1'bx)begin
        last_write_data=dq;last_data_time=$realtime;
    end
    always @(posedge we_n)if(active && writing)begin
        if($realtime-started<70 || $realtime-last_data_time<20)$fatal(1,"CellRAM write pulse/data setup timing");
        index=packed_address(address);words[index]=last_write_data;written[index]=1;writes=writes+1;
        active=0;writing=0;
    end
    always @(posedge ce0_n)if(active && !writing)begin active=0;valid=0;end
endmodule
