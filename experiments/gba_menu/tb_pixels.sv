`timescale 1ns/1ps
module tb_pixels;
    reg bridge=0,memory=0,video=0;
    always #6.734 bridge=~bridge;
    always #4.967 memory=~memory;
    always #59.605 video=~video;
    reg wr=0,request=0,owned=1,show=0,reset=1;
    reg [31:0] addr=0,data=0;
    wire [15:0] pa;wire [17:0] pd;wire we,ack,started,valid,fault,game_ready;
    reg [15:0] game_addr=0;reg game_we=0;
    gba_menu_pixels stream (
        .clk_bridge(bridge),.clk_memory(memory),.bridge_wr(wr),.bridge_endian_little(1'b0),
        .bridge_addr(addr),.bridge_wr_data(data),.menu_owned(owned),.frame_request(request),
        .game_pixel_addr(game_addr),.game_pixel_we(game_we),.pixel_addr(pa),.pixel_data(pd),
        .pixel_we(we),.frame_ack(ack),.frame_started(started),.frame_valid(valid),
        .frame_fault(fault),.game_frame_ready(game_ready));
    wire [23:0] rgb;wire de,vs,hs,skip,visible;
    video_adapter display (
        .clk_sys(memory),.clk_vid(video),.menu_show(show),.menu_fault(1'b0),.menu_visible(visible),
        .reset(reset),.pixel_addr(pa),.pixel_data(pd),.pixel_we(we),
        .video_rgb(rgb),.video_de(de),.video_vs(vs),.video_hs(hs),.video_skip(skip));
    reg [15:0] pixels[0:38399];
    initial $readmemh("pixels.hex",pixels);
    function [17:0] expand(input [15:0] p);
        expand={p[15:11],p[15],p[10:5],p[4:0],p[4]};
    endfunction
    function [23:0] color(input [15:0] p);
        reg [17:0] x;begin x=expand(p);color={x[17:12],x[17:16],x[11:6],x[11:10],x[5:0],x[5:4]};end
    endfunction
    integer writes=0;
    always @(posedge memory)if(we)writes=writes+1;
    task word(input integer pixel_index);
        begin
            @(negedge bridge);addr=32'h50000000+pixel_index*2;
            data={pixels[pixel_index][7:0],pixels[pixel_index][15:8],pixels[pixel_index+1][7:0],pixels[pixel_index+1][15:8]};wr=1;
            @(negedge bridge);wr=0;repeat(74)@(negedge bridge);
        end
    endtask
    task arm;
        begin request=~request;wait(started==request && !valid && !fault);end
    endtask
    integer i,file,count;
    initial begin
        repeat(8)@(negedge video);reset=0;arm;
        for(i=0;i<38398;i=i+2)word(i);
        repeat(100)@(negedge memory);
        if(valid||ack==request||writes!=38398||visible)$fatal(1,"incomplete frame became ready");
        word(38398);wait(valid && ack==request);
        if(writes!=38400)$fatal(1,"lost/duplicate FIFO pixels %0d",writes);
        for(i=0;i<38400;i=i+1)
            if(display.framebuffer[i]!==expand(pixels[i]))$fatal(1,"framebuffer mismatch at %0d",i);
        show=1;wait(visible);@(posedge vs);@(negedge vs);
        file=$fopen("menu.ppm","wb");$fwrite(file,"P6\n240 160\n255\n");count=0;
        while(count<38400)begin
            @(negedge video);
            if(de && !skip)begin
                if(rgb!==color(pixels[count]))$fatal(1,"raster mismatch at %0d: %h expected %h",count,rgb,color(pixels[count]));
                $fwrite(file,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);count=count+1;
            end
        end
        $fclose(file);show=0;wait(!visible);arm;
        word(2);repeat(100)@(negedge memory);
        if(!fault || valid)$fatal(1,"out-of-order frame accepted");
        // Retry wraps the request bit back to the previous successful ack.
        arm;if(valid)$fatal(1,"stale ack accepted on retry");
        for(i=0;i<38400;i=i+2)word(i);
        wait(valid && ack==request);if(fault)$fatal(1,"valid retry rejected");
        owned=0;@(negedge memory);game_addr=38399;game_we=1;
        @(negedge memory);game_we=0;if(game_ready)$fatal(1,"partial game frame exposed");
        @(negedge memory);game_addr=0;game_we=1;
        @(negedge memory);game_addr=38399;
        @(negedge memory);game_we=0;if(!game_ready)$fatal(1,"complete game frame not exposed");
        $display("PASS: actual Intel FIFO + data_loader, all 38400 pixels and raster colors, incomplete/out-of-order rejection, wrapped retry and game handoff");
        $finish;
    end
    initial begin #150000000;$fatal(1,"pixel watchdog");end
endmodule
