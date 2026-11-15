`timescale 1ns/1ps
// Actual upstream loader + Intel FIFO: both Unicode rows, both bridge orders.
module tb_text_ingress;
    reg clk=0;always #7 clk=~clk;
    reg wr=0,little=0;
    reg [31:0] address=0,data=0;
    wire we;wire [27:0] wa;wire [15:0] wd;
    integer got=0,pass_id,n,accepted=0;
    data_loader #(.ADDRESS_MASK_UPPER_4(4'h7),.OUTPUT_WORD_SIZE(2),.WRITE_MEM_CLOCK_DELAY(4)) loader(
        .clk_74a(clk),.clk_memory(clk),.bridge_wr(wr),.bridge_endian_little(little),
        .bridge_addr(address),.bridge_wr_data(data),.write_en(we),.write_addr(wa),.write_data(wd));
    function [15:0] column(input integer x);column=16'hA55A^(16'(x)<<2);endfunction
    always @(posedge clk)if(we && wa[27:11]==17'h02000)begin
        if(wa!==28'h1000000+got*2 || wd!==column(got))
            $fatal(1,"Unicode column lost/duplicated/swapped order=%b at=%h data=%h expected_column=%d",little,wa,wd,got);
        got=got+1;accepted=accepted+1;
    end
    task word_write(input [31:0] at,input [31:0] value,input integer held);
        begin
            @(negedge clk);address=at;
            data=little ? value:{value[7:0],value[15:8],value[23:16],value[31:24]};wr=1;
            repeat(held)@(negedge clk);wr=0;
            repeat(75-held)@(negedge clk);
        end
    endtask
    initial begin
        repeat(16)@(negedge clk);
        for(pass_id=0;pass_id<2;pass_id=pass_id+1)begin
            little=pass_id;got=0;
            // Header traffic shares the 0x7 bridge decoder, but cannot reach
            // the text RAM, whose address comparison is in top_insert.sv.
            for(n=0;n<16;n=n+1)word_write(32'h70000000+n*4,32'h46414247,n%3+1);
            for(n=0;n<512;n=n+1)word_write(32'h71000000+n*4,{column(2*n+1),column(2*n)},n%7+1);
            repeat(128)@(negedge clk);
            if(got!=1024)$fatal(1,"Incomplete Unicode rows %d",got);
        end
        $display("PASS: %0d full 16-bit Unicode columns, two rows, both APF byte orders, held strobes and header isolation, actual upstream loader and Intel FIFO",accepted);$finish;
    end
    initial begin #2000000;$fatal(1,"text ingress watchdog");end
endmodule
