// SPDX-License-Identifier: MIT
`timescale 1ns/1ps
module tb_ws_transfer;
reg bridge=0,memory=0,native=0;
always #6.734006734 bridge=~bridge;
always #4.521122685 memory=~memory;
always #13.563368056 native=~native;
reg wr=0,rd=0,little=0;
reg [31:0] address=0,data=0;
wire save_en,save_idle,read_en,save_ack,sdram_ack;
wire [20:0] save_addr,read_addr;
wire [15:0] save_data,read_data,sdram_data;
wire [31:0] uploaded;
wire [20:0] buffer_addr=save_en?save_addr:read_addr;
ws_data_loader #(.ADDRESS_MASK_UPPER_4(2),.ADDRESS_SIZE(21),.OUTPUT_WORD_SIZE(2),.WRITE_MEM_CLOCK_DELAY(20),.USE_WRITE_COMPLETE(1)) save(
 .clk_74a(bridge),.clk_memory(memory),.bridge_wr(wr),.bridge_endian_little(little),.bridge_addr(address),.bridge_wr_data(data),
 .write_complete(save_ack),.idle(save_idle),.write_en(save_en),.write_addr(save_addr),.write_data(save_data));
data_unloader #(.ADDRESS_MASK_UPPER_4(2),.ADDRESS_SIZE(21),.INPUT_WORD_SIZE(2),.READ_MEM_CLOCK_DELAY(9)) unload(
 .clk_74a(bridge),.clk_memory(native),.bridge_rd(rd),.bridge_endian_little(little),.bridge_addr(address),.bridge_rd_data(uploaded),
 .read_en(read_en),.read_addr(read_addr),.read_data(read_data));
reg [7:0] ramtype=0;
reg [11:0] save_size;
wire has_rtc;
reg cart_download=0;
reg [31:0] rtc_epoch_seconds=1794000000;
reg [79:0] time_dout=0,time_din=0;
reg RTC_load=0,rtc_write_ack=0,tick_rtc=0;
wire clk_sys_36_864=native;
wire sd_buff_wr=save_en,sd_buff_rd=read_en;
wire [20:0] sd_buff_addr=buffer_addr;
wire [15:0] sd_buff_dout=save_data;
always @(posedge native)if(tick_rtc)time_din<=time_din+1'b1;
// The generator inserts the actual wrapper's complete RTC receive/snapshot
// block here; it is not reimplemented by the testbench.
@NATIVE_RTC@
wire eeprom_mode=!saveIsSRAM;
reg [15:0] eeprom[0:16383];
reg [15:0] eeprom_q=0;
reg eeprom_ack=0;
always @(posedge native)begin
 eeprom_q<=eeprom[buffer_addr[14:1]];
 if(save_en && eeprom_mode && !extra_data_addr)eeprom[buffer_addr[14:1]]<=save_data;
 eeprom_ack<=save_en && eeprom_mode && !extra_data_addr;
end
assign read_data=extra_data_addr?sd_buff_din_time:eeprom_mode?eeprom_q:sdram_data;
assign save_ack=extra_data_addr?rtc_write_ack:eeprom_mode?eeprom_ack:sdram_ack;
wire [15:0] dram_output;
reg [15:0] dram_input=0;
wire [12:0] dram_address;
wire [1:0] bank;
wire dqml,dqmh,cs,we,ras,cas;
sdram cart(.SDRAM_DQ(dram_output),.SDRAM_IN(dram_input),.SDRAM_A(dram_address),.SDRAM_BA(bank),.SDRAM_DQML(dqml),.SDRAM_DQMH(dqmh),
 .SDRAM_nCS(cs),.SDRAM_nWE(we),.SDRAM_nRAS(ras),.SDRAM_nCAS(cas),.init(1'b0),.clk(memory),.doRefresh(1'b0),
 .ch1_addr(26'd0),.ch1_req(1'b0),.ch1_rnw(1'b0),.ch1_din(16'd0),
 .ch2_addr({2'b00,4'b1000,buffer_addr[20:1]}),.ch2_req(!eeprom_mode && !extra_data_addr && (save_en||read_en)),.ch2_rnw(!save_en),.ch2_din(save_data),.ch2_dout(sdram_data),.ch2_ready(sdram_ack),
 .ch3_addr(26'd0),.ch3_req(1'b0),.ch3_rnw(1'b0),.ch3_din(16'd0),.ch3_be(2'b11));
reg [12:0] row=0;
reg [15:0] physical_ram[0:262143];
integer physical_writes=0,phase=0,index=0,mode=0,pending=0,payload=0,total=0,mode_index=0,endian_index=0;
reg upload_check=0;
reg [79:0] rtc_seed=0;
reg [95:0] rtc_expected;
reg [24:0] read_index=0,physical_address;
function [7:0] byte_at(input integer offset);
 if(offset<payload)byte_at=(offset*73+31+phase+mode*7)&255;
 else begin
  rtc_expected={upload_check?rtc_snapshot:rtc_seed,16'h5254};
  byte_at=rtc_expected[(offset-payload)*8+:8];
 end
endfunction
function [31:0] word_at(input integer offset);
 word_at=little?{byte_at(offset+3),byte_at(offset+2),byte_at(offset+1),byte_at(offset)}:
                  {byte_at(offset),byte_at(offset+1),byte_at(offset+2),byte_at(offset+3)};
endfunction
always @(negedge memory)begin
 if(pending!=0)begin pending=pending-1;if(pending==0)dram_input=physical_ram[read_index[17:0]];end
 if({ras,cas,we}==3'b011)row=dram_address;
 if({ras,cas,we}==3'b100)begin
  if(dqml || dqmh)$fatal(1,"Native SRAM word enable invalid");
  physical_address={bank,row,dram_address[8:0]};
  if(physical_address[17:0]!=physical_writes || dram_output!={byte_at(physical_writes*2+1),byte_at(physical_writes*2)})
   $fatal(1,"Native SRAM word loss address=%h expected=%d value=%h want=%h mode=%d payload=%d phase=%d",physical_address,physical_writes,dram_output,{byte_at(physical_writes*2+1),byte_at(physical_writes*2)},mode,payload,phase);
  physical_ram[physical_address[17:0]]=dram_output;physical_writes=physical_writes+1;
 end
 if({ras,cas,we}==3'b101)begin read_index={bank,row,dram_address[8:0]};pending=3;end
end
task send_word(input [31:0] at,input [31:0] value);
 begin @(negedge bridge);address=at;data=value;wr=1;
 @(negedge bridge);wr=0;repeat(74)@(negedge bridge);end
endtask
initial begin
 #200000;
 for(mode_index=0;mode_index<9;mode_index=mode_index+1)for(endian_index=0;endian_index<2;endian_index=endian_index+1)begin
  mode=mode_index;phase=endian_index;
  case(mode)
   0:ramtype=0;1:ramtype=1;2:ramtype=2;3:ramtype=3;4:ramtype=4;
   5:ramtype=5;6:ramtype=8'h10;7:ramtype=8'h20;8:ramtype=8'h50;
  endcase
  little=phase;physical_writes=0;tick_rtc=0;upload_check=0;
  rtc_seed=80'h00123456789abcdef0012+mode*7+phase;
  cart_download=1;repeat(20)@(negedge native);cart_download=0;
  repeat(20)@(negedge native);payload=save_size*512;total=payload+12;
  $display("start native save ramtype=%h phase=%0d total=%0d",ramtype,phase,total);$fflush();
  for(index=0;index<total;index=index+4)send_word(32'h20000000+index,word_at(index));
  wait(save_idle);repeat(10)@(negedge native);
  if(!eeprom_mode && physical_writes!=payload/2)$fatal(1,"SRAM load released before drain");
  if(!RTC_load || time_dout!=rtc_seed)$fatal(1,"RTC import mismatch got=%h want=%h",time_dout,rtc_seed);
  // A late host upload runs with gameplay already stopped. RTC keeps ticking;
  // the snapshot must make all six transmitted halfwords one coherent value.
  time_din=time_dout;tick_rtc=1;upload_check=1;
  for(index=0;index<total;index=index+4)begin
   @(negedge bridge);address=32'h20000000+index;rd=1;
   @(negedge bridge);rd=0;repeat(74)@(negedge bridge);
   if(uploaded!=word_at(index))$fatal(1,"Save upload mismatch memory=%d endian=%d offset=%h got=%h want=%h",mode,little,index,uploaded,word_at(index));
  end
  $display("PASS: ramtype=%h endian=%0d %0d bytes including all RTC bytes; 75-clock APF spacing; actual SDRAM FSM+CAS3 model or EEPROM port; RTC download/snapshot coherent",ramtype,phase,total);$fflush();
  repeat(100)@(negedge bridge);
 end
 $finish;
end
initial begin #(64'd3000000000);$fatal(1,"Native transfer watchdog");end
endmodule
