`timescale 1ns/1ps
module tb_ws_lifecycle;
reg clk=0;always #6.734 clk=~clk;
reg ready=0,bw=0,br=0;reg [31:0] buttons=0,ba=0,bd=0;
wire [31:0] param;wire rd,wr,op,fl;
wire [15:0] slot;wire [31:0] off,address,length;
reg done=1;reg [2:0] error=0;
wire owned,show,rst,paused,new_load,finish_load,bound,fault;
wire [7:0] code,state,first_code;wire [10:0] selected;
wire cf_menu;wire [3:0] level_target,title_target;
reg [3:0] level=0,title_level=0;
reg prepare_ready=1,load_ready=1,loading=0,pause_ack=0;
reg [31:0] capacity=12;
wire [1:0] bios;
wire [31:0] expected_save,cart_config;
ws_menu #(.TIMEOUT(34'd10000),.SETTLE_CYCLES(20'd16),.FRAME_TIMEOUT(34'd8000)) dut(
 .clk(clk),.ready(ready),.buttons(buttons),.bridge_wr(bw),.bridge_rd(br),.bridge_endian_little(1'b0),
 .bridge_addr(ba),.bridge_wr_data(bd),.param_rd_data(param),
 .t_read(rd),.t_write(wr),.t_open(op),.t_flush(fl),.t_slot(slot),.t_offset(off),.t_address(address),.t_length(length),
 .t_done(done),.t_error(error),.frame_ack(1'b0),.frame_started(1'b0),.frame_valid(1'b0),.frame_fault(1'b0),
 .visible(cf_menu && level!=0),.prepare_ready(prepare_ready),.load_ready(load_ready),
 .io_idle(!loading && (!bound || pause_ack)),.save_capacity(capacity),.pause_allowed(1'b1),
 .rom_config(cart_config),.expected_save(expected_save),.bios_select(bios),.bios_idle(1'b1),
 .cf_want_art(1'b0),.cf_wanted_game(11'd0),.cf_anim(1'b0),.cf_frame_tick(1'b1),
 .cf_mem_idle(1'b1),.cf_fetch_fault(1'b0),.cf_upload_ready(1'b1),.cf_wanted_slot(3'd0),
 .cf_level(level),.cf_title_level(title_level),.cf_menu(cf_menu),.cf_level_target(level_target),.cf_title_target(title_target),
 .menu_owned(owned),.menu_show(show),.menu_reset(rst),.menu_pause(paused),
 .new_load(new_load),.finish_load(finish_load),.game_bound(bound),.fault(fault),.fault_code(code),.first_fault_code(first_code),.state(state),.selected(selected));
always @(posedge clk)begin level<=level_target;title_level<=title_target;end
reg [7:0] page[0:1000000];initial $readmemh("child.hex",page);
integer reads=0,writes=0,flushes=0,opens=0,bios_reads=0,launches=0;
reg fail_flush=0,fail_save_read=0,missing_save=0,wrong_capacity=0,stall_done=0;
reg fail_bios=1;
integer at,n,p,flags_before,write_before;
reg [31:0] word,flags,size;
reg [2047:0] opened;
task parameter_word(input integer at,output reg[31:0] value);
 begin @(negedge clk);ba=at;br=1;repeat(5)@(negedge clk);value=param;br=0;end
endtask
task reply(input [2:0] result);
 begin repeat(4)@(negedge clk);error=result;done=1;end
endtask
initial forever begin
 @(negedge clk);
 if(rd||wr||op||fl)begin
  done=0;error=0;
  if(stall_done)begin end
  else if(op)begin
   opened=0;
   for(p=0;p<64;p=p+1)begin
    parameter_word(32'hf3000000+p*4,word);
    for(n=0;n<4;n=n+1)if(word[31-n*8-:8]!=0)opened={opened[2039:0],word[31-n*8-:8]};
   end
   parameter_word(32'hf3000100,flags);parameter_word(32'hf3000104,size);
   if(flags!=0 || size!=0)$fatal(1,"open attempted to create/truncate a file");
   if(slot!=0 && slot!=11 && slot!=100)$fatal(1,"wrong open slot");
   if(slot==11 && (opened[31:0] != ".sav"))$fatal(1,"ordinary save path mismatch");
   opens=opens+1;
   if(slot==11 && missing_save)reply(3);else reply(0);
  end else if(rd)begin
   case(slot)
    9,10:begin
     if(bios!=(slot==9 ? 1:2) || address!=32'h30000000 || length!=(slot==9 ? 4096:8192))$fatal(1,"BIOS selection/mapping");
     bios_reads=bios_reads+1;
     if(fail_bios)begin fail_bios=0;reply(3);end else reply(0);
    end
    100:begin
     if(address==32'h70000000 || address==32'h60000000)
      for(at=0;at<length;at=at+4)begin
       @(negedge clk);ba=address+at;bd={page[off+at],page[off+at+1],page[off+at+2],page[off+at+3]};bw=1;
       @(negedge clk);bw=0;
      end
     else if(address!=32'h71000000)$fatal(1,"unexpected menu read");
     reply(0);
    end
    0:begin
     if(!rst || bound || !loading || address!=32'h10000000 || length!=131072)$fatal(1,"unsafe ROM load");
     case(selected)
      0:capacity=12;1:capacity=8204;2:capacity=32780;3:capacity=131084;4:capacity=262156;
      5:capacity=524300;6,7,8:capacity=2060;default:$fatal(1,"wrong ROM selection");
     endcase
     if(wrong_capacity)capacity=1234;
     reads=reads+1;reply(0);
    end
    11:begin
     if(!rst || bound || address!=32'h20000000 || length!=capacity)$fatal(1,"save/RTC read length");
     prepare_ready=0;
     if(fail_save_read)begin prepare_ready=1;reply(4);end
     else begin
      reply(0);repeat(30)@(negedge clk);
      if(!rst || bound)$fatal(1,"released native engine before save loader drained");
      prepare_ready=1;
     end
    end
    default:$fatal(1,"unexpected read slot");
   endcase
  end else if(wr)begin
   if(!bound || !paused || !pause_ack || rst || slot!=11 || address!=32'h20000000 || length!=capacity)
     $fatal(1,"unsafe ordinary save write");
   writes=writes+1;reply(0);
  end else if(fl)begin
   if(!bound || !paused || rst || slot!=11)$fatal(1,"reset/unbound before flush completed");
   if(fail_flush)begin fail_flush=0;reply(4);end
   else begin flushes=flushes+1;reply(0);end
  end
  wait(!(rd||wr||op||fl));
 end
end
always @(posedge new_load)begin
 launches=launches+1;load_ready<=0;loading<=1;
end
always @(posedge finish_load)begin
 if(!prepare_ready)$fatal(1,"finish before FIFO drain");
 loading<=0;repeat(32)@(negedge clk);load_ready<=1;
end
always @(posedge paused)begin repeat(16)@(negedge clk);pause_ack<=1;end
always @(negedge paused)pause_ack<=0;
always @(negedge clk)begin
 if(!owned && (!bound || rst || !load_ready))$fatal(1,"engine released before all fences");
 if(fault && !bound)loading<=0;
end
task key(input integer k);
 begin @(negedge clk);buttons=1<<k;repeat(4)@(negedge clk);buttons=0;repeat(4)@(negedge clk);end
endtask
task menu(input integer index);
 begin wait(state==13 && selected==index && level==8 && title_level==8);repeat(5)@(negedge clk);end
endtask
task run_game;
 begin wait(state==32 && bound && !rst && !owned);repeat(5)@(negedge clk);end
endtask
task pause_game;
 begin @(negedge clk);buttons=(1<<8)|(1<<9)|(1<<14);repeat(4)@(negedge clk);buttons=0;
  wait(state==34 && pause_ack);repeat(5)@(negedge clk);end
endtask
task save_return;
 begin pause_game;key(1);wait(dut.pause_option==1);key(4);end
endtask
integer game;
initial begin
 #100;ready=1;
 wait(fault);if(code!=8'h80 || bound || !rst)$fatal(1,"missing BIOS error is unsafe");
 key(4);menu(0);if(bios_reads!=3 || bios!=0)$fatal(1,"BIOS retry failed");
 key(4);run_game;
 pause_game;key(5);run_game;
 fail_flush=1;save_return;wait(fault);
 if(code!=8'h54 || !bound || rst || !paused)$fatal(1,"failed flush discarded progress");
 write_before=writes;repeat(100)@(negedge clk);
 if(writes!=write_before)$fatal(1,"save retries without user input");
 key(5);run_game;save_return;menu(0);
 for(game=1;game<9;game=game+1)begin
  key(3);menu(game);key(4);run_game;save_return;menu(game);
 end
 if(reads!=9 || launches!=9 || flushes!=9 || writes!=10)$fatal(1,"all native save lengths not covered");
 missing_save=1;key(4);wait(fault);
 if(code!=8'h40 || bound || !rst)$fatal(1,"missing progress was implicitly replaced");
 missing_save=0;key(5);menu(0);
 wrong_capacity=1;key(4);wait(fault);
 if(code!=8'h34 || bound || !rst)$fatal(1,"header/native save mismatch accepted");
 wrong_capacity=0;key(5);menu(0);
 fail_save_read=1;key(4);wait(fault);
 if(code!=8'h42 || bound || !rst)$fatal(1,"failed save read released native engine");
 fail_save_read=0;key(5);menu(0);
 stall_done=1;key(4);wait(fault);
 if(code!=8'hfe || bound || !rst)$fatal(1,"APF timeout unsafe");
 key(5);repeat(30)@(negedge clk);if(!fault)$fatal(1,"in-flight APF command escaped error fence");
 done=1;stall_done=0;key(5);menu(0);
 $display("PASS WS lifecycle: BIOS retry; nine ROM headers, seven save lengths; pause/resume; write+flush fences; missing/read-failed saves and mismatch fail closed; no automatic save retry; APF timeout holds reset");
 $finish;
end
initial begin #20000000;$fatal(1,"watchdog state=%d fault=%h selection=%d",state,code,selected);end
endmodule
