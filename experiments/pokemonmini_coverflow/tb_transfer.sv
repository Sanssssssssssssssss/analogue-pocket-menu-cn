// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_pm_transfer;
reg bridge=0,memory=0,native=0;
always #6.734006734 bridge=~bridge;
always #12.500001563 memory=~memory;
always #15.625002441 native=~native;
reg wr=0,rd=0,little=0;
reg [31:0] address=0,data=0;
wire rom_en,rom_idle,save_en,save_idle,read_en;
wire [24:0] rom_addr;
wire [12:0] save_addr,read_addr;
wire [7:0] rom_data,save_data,read_data;
wire [31:0] uploaded;
pm_data_loader #(.ADDRESS_MASK_UPPER_4(1),.ADDRESS_SIZE(25),.WRITE_MEM_CLOCK_DELAY(8),.WRITE_MEM_EN_CYCLE_LENGTH(5)) rom(
 .clk_74a(bridge),.clk_memory(memory),.bridge_wr(wr),.bridge_endian_little(little),.bridge_addr(address),.bridge_wr_data(data),
 .idle(rom_idle),.write_en(rom_en),.write_addr(rom_addr),.write_data(rom_data));
pm_data_loader #(.ADDRESS_MASK_UPPER_4(2),.ADDRESS_SIZE(13),.WRITE_MEM_CLOCK_DELAY(6),.WRITE_MEM_EN_CYCLE_LENGTH(2)) save(
 .clk_74a(bridge),.clk_memory(native),.bridge_wr(wr),.bridge_endian_little(little),.bridge_addr(address),.bridge_wr_data(data),
 .idle(save_idle),.write_en(save_en),.write_addr(save_addr),.write_data(save_data));
data_unloader #(.ADDRESS_MASK_UPPER_4(2),.ADDRESS_SIZE(13),.READ_MEM_CLOCK_DELAY(2)) unload(
 .clk_74a(bridge),.clk_memory(native),.bridge_rd(rd),.bridge_endian_little(little),.bridge_addr(address),.bridge_rd_data(uploaded),
 .read_en(read_en),.read_addr(read_addr),.read_data(read_data));
eeprom storage(.clk(native),.clk_ce(1'b0),.reset(1'b0),.ce(1'b0),.data_in(1'b1),
 .rom_we(save_en),.rom_address_in(save_en?save_addr:read_addr),.rom_data_in(save_data),.rom_data_out(read_data));
wire [15:0] dram_data;
wire [12:0] dram_address;
wire [1:0] bank;
wire dqml,dqmh,cs,we,ras,cas;
sdram cart(.SDRAM_DQ(dram_data),.SDRAM_A(dram_address),.SDRAM_BA(bank),.SDRAM_DQML(dqml),.SDRAM_DQMH(dqmh),
 .SDRAM_nCS(cs),.SDRAM_nWE(we),.SDRAM_nRAS(ras),.SDRAM_nCAS(cas),.init(1'b0),.clk(memory),
 .ch0_addr(rom_addr),.ch0_rd(1'b0),.ch0_wr(rom_en),.ch0_din(rom_data),
 .ch1_addr(25'd0),.ch1_rd(1'b0),.ch1_wr(1'b0),.ch1_din(8'd0),
 .ch2_addr(25'd0),.ch2_rd(1'b0),.ch2_wr(1'b0),.ch2_din(8'd0));
reg [12:0] row=0;
integer physical_writes=0,save_writes=0,phase=0,index=0;
reg [24:0] physical_address;
reg save_prev=0;
function [7:0] byte_at(input integer offset);byte_at=(offset*73+31+phase)&255;endfunction
function [31:0] word_at(input integer offset);
 word_at=little?{byte_at(offset+3),byte_at(offset+2),byte_at(offset+1),byte_at(offset)}:
                  {byte_at(offset),byte_at(offset+1),byte_at(offset+2),byte_at(offset+3)};
endfunction
always @(negedge memory)begin
 if({ras,cas,we}==3'b011)row=dram_address;
 if({ras,cas,we}==3'b100)begin
  if(dqml==dqmh)$fatal(1,"Native ROM byte enable invalid");
  physical_address={bank,dram_address[8:0],row,dqml};
  if(physical_address!=physical_writes || dram_data[7:0]!=byte_at(physical_writes))
   $fatal(1,"Native ROM loss/duplication address=%d expected=%d value=%h",physical_address,physical_writes,dram_data);
  physical_writes=physical_writes+1;
 end
end
always @(negedge native)begin
 if(save_en && !save_prev)begin
  if(save_addr!=save_writes || save_data!=byte_at(save_writes))$fatal(1,"EEPROM byte lost");
  save_writes=save_writes+1;
 end
 save_prev=save_en;
end
task send_word(input [31:0] at,input [31:0] value);
 begin @(negedge bridge);address=at;data=value;wr=1;
 @(negedge bridge);wr=0;repeat(74)@(negedge bridge);end
endtask
initial begin
 #200000;
 for(phase=0;phase<2;phase=phase+1)begin
  little=phase;physical_writes=0;save_writes=0;
  for(index=0;index<32768;index=index+4)send_word(32'h10000000+index,word_at(index));
  wait(rom_idle);if(physical_writes!=32768)$fatal(1,"ROM drain released early %d",physical_writes);
  for(index=0;index<8192;index=index+4)send_word(32'h20000000+index,word_at(index));
  wait(save_idle);if(save_writes!=8192)$fatal(1,"Save drain released early");
  for(index=0;index<8192;index=index+4)begin
   @(negedge bridge);address=32'h20000000+index;rd=1;
   @(negedge bridge);rd=0;repeat(74)@(negedge bridge);
   if(uploaded!=word_at(index))$fatal(1,"Save upload mismatch endian=%d offset=%h got=%h want=%h",little,index,uploaded,word_at(index));
  end
  $display("PASS: endian=%0d 32768 physical SDRAM byte writes, 8192 EEPROM load/readback bytes, 75-clock APF spacing, native FIFO drain",phase);
 end
 $finish;
end
initial begin #100000000;$fatal(1,"Native transfer watchdog");end
endmodule
