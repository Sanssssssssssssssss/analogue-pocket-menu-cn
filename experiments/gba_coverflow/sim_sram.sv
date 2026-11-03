`timescale 1ns/1ps
// Datasheet-based AS6C2016-55 model, not a vendor or physical-board model.
// Address/control launch and read return each include a 4.25 ns I/O budget.
module sim_coverflow_sram (
    input wire clock,
    input wire [16:0] a,
    inout wire [15:0] dq,
    input wire oe_n,we_n,ub_n,lb_n,
    output integer reads=0,writes=0
);
    localparam realtime IO=4.25;
    wire [16:0] pa;wire po,pw,pu,pl;
    assign #(IO) pa=a;
    assign #(IO) po=oe_n;assign #(IO) pw=we_n;
    assign #(IO) pu=ub_n;assign #(IO) pl=lb_n;
    reg [15:0] words[0:131071];
    reg written[0:131071];
    integer n;
    initial for(n=0;n<131072;n=n+1)written[n]=0;
    wire reading=!po && pw && !pu && !pl;
    reg [15:0] value=16'hxxxx;
    reg valid=0;
    // Observe on half-cycles, after the 55 ns access and I/O return budget.
    // This avoids both delta-cycle admission races and whole-array sensitivity.
    realtime address_changed=0,data_changed=0,write_started=0,bytes_started=0;
    realtime output_started=0,output_ended=0;
    always @(posedge reading)output_started=$realtime;
    always @(negedge reading)output_ended=$realtime;
    always @(negedge clock)begin
        if(reading)begin
            if($realtime-address_changed>=55+IO && $realtime-bytes_started>=55+IO && $realtime-output_started>=30+IO)begin
                if(!written[pa])$fatal(1,"SRAM read before atlas upload addr=%h",pa);
                value=words[pa];valid=1;
            end else valid=0;
        end else if($realtime-output_ended>=25+IO)valid=0;
    end
    assign dq=valid ? value:16'hzzzz;
    reg writing=0;
    always @(pa)begin
        if(writing)$fatal(1,"SRAM address changed during a write");
        address_changed=$realtime;
        if(reading)reads=reads+1;
    end
    always @(posedge reading)reads=reads+1;
    always @(dq)if(writing && (^dq)!==1'bx)data_changed=$realtime;
    always @(negedge pu or negedge pl)bytes_started=$realtime;
    always @(negedge pw)begin
        if(!po || pu || pl)$fatal(1,"unsafe SRAM write admission");
        writing=1;write_started=$realtime;
    end
    always @(posedge pw)if(writing)begin
        if($realtime-write_started<45 || $realtime-address_changed<50 ||
           $realtime-bytes_started<50 || $realtime-data_changed<25 || (^dq)===1'bx)
            $fatal(1,"SRAM write timing/data requirement failed");
        if(pa>=113920)$fatal(1,"cover write escaped the five packed slots");
        words[pa]=dq;written[pa]=1;writes=writes+1;writing=0;
    end
endmodule
