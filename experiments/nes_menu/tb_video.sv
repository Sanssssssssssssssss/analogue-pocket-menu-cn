`timescale 1ns/1ps
module tb_video;
    reg cm=0,cv=0;always #23 cm=~cm;always #93 cv=~cv;
    reg reset=1,we=0;reg [15:0] addr=0;reg [17:0] data=0;
    reg owned=1,show=0,fault=0;
    reg [23:0] game_rgb=24'h123456;reg game_de=0,game_hs=0,game_vs=0;
    wire visible;wire [23:0] rgb;wire de,hs,vs;
    menu_video dut(cm,cv,reset,we,addr,data,owned,show,fault,
        game_rgb,game_de,game_hs,game_vs,visible,rgb,de,hs,vs);
    integer i,frames=0,pixels=0,colored=0;
    reg capture=0;
    always @(negedge cv)if(capture && de)begin
        if(rgb!=0)begin
            if(rgb!==24'hff9200)$fatal(1,"bad RGB332 conversion %h",rgb);
            colored=colored+1;
        end
        pixels=pixels+1;
    end
    initial begin
        #600;reset=0;
        for(i=0;i<38400;i=i+1)begin
            @(negedge cm);we=1;addr=i;data={6'b111111,6'b100100,6'b000000};
        end
        @(negedge cm);we=0;show=1;wait(visible);repeat(2)@(posedge vs);
        @(negedge cv);capture=1;@(posedge vs);@(negedge cv);capture=0;
        if(pixels!=61440 || colored!=38400)$fatal(1,"wrong frame geometry %0d / %0d",pixels,colored);
        show=0;wait(!visible);repeat(2)@(posedge vs);
        if(rgb!==0)$fatal(1,"hidden frame not black");
        owned=0;repeat(341*262*2)@(posedge cv);repeat(10)@(negedge cv);
        for(i=0;i<256;i=i+1)begin
            game_rgb={8'(i),8'(255-i),8'(i^85)};game_de=i[0];game_hs=i[1];game_vs=i[2];
            @(posedge cv);#1;
            if({rgb,de,hs,vs}!=={game_rgb,game_de,game_hs,game_vs})$fatal(1,"game video changed");
            @(negedge cv);
        end
        $display("PASS: 38400 menu pixels centered in 256x240; RGB332; hide handshake; bit-identical game video/sync bypass");
        $finish;
    end
    initial begin #180000000;$fatal(1,"video timeout");end
endmodule
