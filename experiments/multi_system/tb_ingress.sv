`timescale 1ns/1ps
// Runs the actual frozen GBA and NES input modules with Intel's FIFO model.
module tb_ingress;
    reg bridge_clk=0;always #7 bridge_clk=~bridge_clk;
    reg memory_clk=0;always #23 memory_clk=~memory_clk;
    reg wr=0,little=1,completion=0,ready=1,fence_ready=0;
    reg [31:0] addr=0,data=0;
    wire gv,fv,fd,busy,nv;
    wire [1:0] gd;
    wire [27:0] ga,na;
    wire [15:0] gdata;
    wire [7:0] ndata;
    apf_write_ingress gba(bridge_clk,memory_clk,wr,little,addr,data,completion,
                         gv,gd,ga,gdata,ready,fv,fence_ready,fd,busy);
    data_loader #(.ADDRESS_MASK_UPPER_4(1)) nes(
        .clk_74a(bridge_clk),.clk_memory(memory_clk),.bridge_wr(wr),
        .bridge_endian_little(little),.bridge_addr(addr),.bridge_wr_data(data),
        .write_en(nv),.write_addr(na),.write_data(ndata));
    reg [15:0] expected_g [0:7];
    reg [27:0] expected_ga [0:7];
    reg [1:0] expected_gd [0:7];
    reg [7:0] expected_n [0:7];
    integer gi=0,ni=0,fences=0;
    always @(posedge memory_clk) begin
        if(gv&&ready)begin
            if(gi>=8||gdata!==expected_g[gi]||ga!==expected_ga[gi]||gd!==expected_gd[gi])
                $fatal(1,"GBA byte/address/region mismatch index %0d: %h %h %h",gi,gdata,ga,gd);
            gi=gi+1;
        end
        if(nv)begin
            if(ni>=8||ndata!==expected_n[ni]||na!==ni)
                $fatal(1,"NES byte/address mismatch index %0d: %h %h",ni,ndata,na);
            ni=ni+1;
        end
        if(fd)begin
            if(gi!=8)$fatal(1,"completion overtook data");
            fences=fences+1;
        end
    end
    task send(input[31:0] a,input[31:0] d,input endian);
        @(negedge bridge_clk);addr=a;data=d;little=endian;wr=1;
        @(negedge bridge_clk);wr=0;
        repeat(220)@(negedge bridge_clk);
    endtask
    reg [45:0] stalled;
    initial begin
        expected_g[0]=16'h454e;expected_g[1]=16'h1a53;
        expected_g[2]=16'h2301;expected_g[3]=16'h6745;
        expected_g[4]=16'hcdef;expected_g[5]=16'h89ab;
        expected_g[6]=16'h3210;expected_g[7]=16'h7654;
        expected_ga[0]=0;expected_ga[1]=2;expected_ga[2]=4;expected_ga[3]=6;
        expected_ga[4]=0;expected_ga[5]=2;expected_ga[6]=0;expected_ga[7]=2;
        expected_gd[0]=1;expected_gd[1]=1;expected_gd[2]=1;expected_gd[3]=1;
        expected_gd[4]=2;expected_gd[5]=2;expected_gd[6]=3;expected_gd[7]=3;
        expected_n[0]=8'h4e;expected_n[1]=8'h45;expected_n[2]=8'h53;expected_n[3]=8'h1a;
        expected_n[4]=8'h01;expected_n[5]=8'h23;expected_n[6]=8'h45;expected_n[7]=8'h67;
        repeat(20)@(negedge bridge_clk);
        ready=0;
        fork
            send(32'h10000000,32'h1a53454e,1);
            begin
                wait(gv);@(negedge memory_clk);stalled={gd,ga,gdata};
                repeat(12)begin
                    @(negedge memory_clk);
                    if(!gv||{gd,ga,gdata}!==stalled)$fatal(1,"GBA backpressure changed a word");
                end
                ready=1;
            end
        join
        send(32'h10000004,32'h01234567,0);
        send(32'h20000000,32'h89abcdef,1);
        send(32'h30000000,32'h10325476,0);
        send(32'h40000000,32'hffffffff,1); // ignored by both real modules
        @(negedge bridge_clk);completion=1;
        @(negedge bridge_clk);completion=0;
        wait(fv);repeat(12)@(negedge memory_clk);
        if(fd||fences)$fatal(1,"completion ignored physical-write fence");
        fence_ready=1;wait(fences==1);repeat(4)@(negedge memory_clk);
        if(gi!=8||ni!=8)$fatal(1,"missing data");
        if($test$plusargs("reload"))begin
            // Current upstream treats ingress as startup-only and rejects this.
            send(32'h10000000,32'h00000000,1);
            $fatal(1,"expected upstream reload guard was absent");
        end
        $display("PASS: real GBA/NES ingress, Intel FIFO model, endian conversion, address filters, backpressure and completion fence");
        $finish;
    end
    initial begin #200000; $fatal(1,"ingress watchdog"); end
endmodule
