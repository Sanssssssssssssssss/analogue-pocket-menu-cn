#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a source-pinned native Arduboy CoverFlow candidate offline."""
import argparse,hashlib,importlib.util,json,re,shutil,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
REPO='https://github.com/agg23/openfpga-arduboy'
COMMIT='82bc07fcb14126d96e9d5489bdf5b30e3694769f'
ARCHIVE_SHA='3bd84c77c8e681430dd8b9c9280e284c8a0355a7a298b644e7f6d2524f39c95a'
NAMESPACE='ardlab'
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
base=load('ard_console_prepare',ROOT/'experiments/console_coverflow/prepare.py')
replace=base.replace

def controller():
    base.PROFILES['pce']=(NAMESPACE,1024,262144,0x20000000,'')
    s=base.controller('pce').replace('module console_menu #','module arduboy_menu #',1)
    s=replace(s,"localparam [31:0] PARAM=32'hF3000000;","localparam [31:0] PARAM=32'hF4000000;")
    s=replace(s,'input wire [31:0] save_capacity,','input wire clear_ready,cart_fault,\n    input wire [31:0] save_capacity,')
    s=replace(s,'rom_bytes<512 || rom_bytes>262144 || rom_bytes[1:0]!=0 || cart_mode>1',
        'rom_bytes<12 || rom_bytes>262144 || cart_mode<2 || cart_mode>32768')
    s=replace(s,'if(!validate_rtc)begin validate_rtc<=1;validate_index<=0;row_read_addr<=136;state<=VALIDATE_WAIT;end\n                    else if(go_back)',
        'if(go_back)')
    # State 53 is the shared renderer's hard-coded commit handoff bubble.
    s=replace(s,'    localparam CF_TEXT_WAIT=47,','    localparam ROM_CLEAR=60;\n    localparam CF_TEXT_WAIT=47,')
    s=replace(s,"ROM_OPENED:if(result!=0)fail(8'h32);else command(0,0,0,32'h10000000,rom_bytes,ROM_READ);",
        "ROM_OPENED:if(result!=0)fail(8'h32);else begin state<=ROM_CLEAR;timer<=0;end\n            ROM_CLEAR:if(clear_ready)command(0,0,0,32'h00000000,rom_bytes,ROM_READ);\n                else if(timer>=TIMEOUT)fail(8'h36);")
    s=replace(s,'ROM_SETTLE:if(timer>=SETTLE_CYCLES && prepare_ready)begin',
        "ROM_SETTLE:if(cart_fault)fail(8'h37);else if(timer>=SETTLE_CYCLES && prepare_ready)begin")
    s=replace(s,'            LOAD_DRAIN:if(load_ready && drain_was_low)begin',
        "            LOAD_DRAIN:if(cart_fault)fail(8'h38);else if(load_ready && drain_was_low)begin")
    # Native Pocket Quit remains responsible for flushing the bound EEPROM.
    # No in-game pause implementation is exposed by this menu.
    a=s.index('            PAUSE_WAIT:');b=s.index('            ERROR:',a);s=s[:a]+s[b:]
    s=replace(s,'if(game_bound)begin state<=QUIT_WAIT;timer<=0;end else state<=HOME_OPEN;',
        'if(game_bound)begin menu_owned<=0;menu_pause<=0;state<=RUN;end else state<=HOME_OPEN;')
    return s

def prepare(archive,out,gba_source):
    base.PROFILES['pce']=(NAMESPACE,1024,262144,0x20000000,'')
    out=base.nes.extract_source(archive,out,ARCHIVE_SHA)
    dest=out/'src/fpga/core';project=out/'src/fpga';top=dest/'core_top.sv'
    s=top.read_text(encoding='utf8')
    s,n=re.subn(r'^\s*assign cram0_[a-z0-9_]+\s*=.*?;\s*$','',s,flags=re.M)
    if n!=11:raise ValueError('CRAM0 is not completely unused')
    s=replace(s,"      32'hF8??????:","      32'hF4??????: begin bridge_rd_data=ui_param;end\n      32'hF8??????:")
    s=replace(s,'eeprom_save_rd_74a ? eeprom_bridge_rd_data','(eeprom_save_rd_74a || ui_bound) ? eeprom_bridge_rd_data')
    s=replace(s,"EEPROM_DATATABLE_ADDR = 10'd3;","EEPROM_DATATABLE_ADDR = 10'd5;")
    s=replace(s,'.datatable_data         ( EEPROM_BYTES ),','.datatable_data         ( eeprom_valid ? EEPROM_BYTES : 0 ),')
    s=replace(s,'                    .datatable_addr         ( EEPROM_DATATABLE_ADDR ),',
        '''                    .target_cmd_req(tcmd_req),.target_cmd(tcmd),
                    .target_cmd_p0(tcmd_p0),.target_cmd_p1(tcmd_p1),.target_cmd_p2(tcmd_p2),.target_cmd_p3(tcmd_p3),
                    .target_cmd_ack(tcmd_ack),.target_cmd_done(tcmd_done),.target_cmd_result(tcmd_result),
                    .datatable_addr         ( EEPROM_DATATABLE_ADDR ),''')
    s=replace(s,'.reset_n(1),','.reset_n(reset_n && !ui_new),')
    # Clear all program bytes before loading a HEX file. Sparse HEX files must
    # not inherit instructions from an earlier game. Preserve the upstream RAM.
    s=replace(s,'    if(write_en)\n    begin\n      rom[write_addr[14:1]][write_addr[0]] <= write_data;\n    end',
        '''    if(!reset_n || ui_new)begin rom_clear<=0;rom_written<=0;end
    else if(!rom_clear[15])rom_clear<=rom_clear+1'b1;
    else if(write_en)rom_written<=rom_written+1'b1;
    if(!rom_clear[15] || write_en)rom[rom_write_address[14:1]][rom_write_address[0]]<=rom_write_data;''')
    s=replace(s,'  wire write_en;',"  reg [15:0] rom_clear=0;\n  reg [31:0] rom_written=0;\n  wire [14:0] rom_write_address=rom_clear[15] ? write_addr:rom_clear[14:0];\n  wire [7:0] rom_write_data=rom_clear[15] ? write_data:8'hff;\n  wire write_en;")
    s=replace(s,'.core_rst(~reset_n),','.core_rst(~reset_n || ui_reset_avr),')
    s=replace(s,'.dev_rst(~reset_n),','.dev_rst(~reset_n || ui_reset_avr),')
    s=replace(s,'  data_loader #(\n                .ADDRESS_MASK_UPPER_4', '  ard_eeprom_loader #(\n                .ADDRESS_MASK_UPPER_4')
    a=s.index('  data_unloader #(');b=s.index('  ard_eeprom_loader #(',a)
    s=s[:a]+'''  // Mirror every real EEPROM commit; bridge reads cannot wait for
  // four serial bytes from a 16MHz peripheral through the original unloader.
  wire eep_commit;wire [9:0] eep_commit_address;wire [7:0] eep_commit_data;
  assign eeprom_rd=0;assign eeprom_addr_out=0;
  ard_eeprom_shadow save_shadow(.clk_avr(clk_avr_16),.clk_bridge(clk_74a),
      .write_en(eep_commit),.write_address(eep_commit_address),.write_data(eep_commit_data),
      .bridge_address(bridge_addr),.bridge_endian_little(bridge_endian_little),.bridge_data(eeprom_bridge_rd_data));

'''+s[b:]
    s=replace(s,'                       .ext_eep_data_o(eeprom_data_out),',
        '''                       .ext_eep_data_o(eeprom_data_out),
                       .eep_commit_o(eep_commit),.eep_commit_addr_o(eep_commit_address),.eep_commit_data_o(eep_commit_data),''')
    s=s.replace('eeprom_wr & eeprom_save_wr_avr','eeprom_wr & (eeprom_save_wr_avr || ui_eep_loading_avr)')
    s=s.replace('eeprom_rd & eeprom_save_rd_avr','eeprom_rd & (eeprom_save_rd_avr || ui_bound_avr)')
    for sig,port in [('vs','v_sync'),('hs','h_sync'),('de','video_en')]:
        s=replace(s,f'.{port}(video_{sig})',f'.{port}(console_game_{sig})')
    s=replace(s,'  assign video_skip = 0;','')
    s=replace(s,"assign video_rgb = video_de && video_out ? 24'hFFFFFF : 24'h0;",
        "assign console_game_rgb = console_game_de && video_out ? 24'hFFFFFF : 24'h0;")
    s=replace(s,'assign audio_left = buzzer_1_in && buzzer_2_in ? 0 : buzzer_1_audio + buzzer_2_audio;',
        'assign audio_left = ui_owned || (buzzer_1_in && buzzer_2_in) ? 0 : buzzer_1_audio + buzzer_2_audio;')
    a=s.index('  assign audio_mclk = audgen_mclk;');b=s.index('  ///////////////////////////////////////////////',a)
    s=s[:a]+'''  ard_audio native_audio(.clk(clk_74a),.buzzer1(Buzzer1),.buzzer2(Buzzer2),
      .enable1(buzzer1_en),.enable2(buzzer2_en),.limit_volume(limit_volume),.mute(ui_owned),
      .mclk(audio_mclk),.lrck(audio_lrck),.dac(audio_dac));

'''+s[b:]
    insertion=base.insert('pce','clk_video_1_25','menu_pixel_ce',1).replace('console_menu menu(','arduboy_menu menu(',1)
    insertion=replace(insertion,".prepare_ready(1'b1),.load_ready(!ui_loading && ui_settle==0),",
        ".clear_ready(rom_clear[15]),.cart_fault(rom_written>ui_cart_mode || eep_fault),\n      .prepare_ready(rom_written==ui_cart_mode),.load_ready(!ui_loading && ui_settle==0 && eep_written==1024),")
    insertion=replace(insertion,'.enable(cf_menu && !ui_fault),','.enable(cf_menu || !ui_bound || ui_fault),')
    insertion=replace(insertion,'cf_menu || ui_fault','cf_menu || !ui_bound || ui_fault')
    insertion=replace(insertion,'cf_de ? cf_rgb :','cf_de ? (ui_fault ? ard_error_rgb:cf_rgb) :')
    insertion+='''
  // This PLL net is named 1.25MHz upstream but is actually 46.476188MHz.
  reg [2:0] menu_div=0;
  always @(posedge clk_video_1_25)menu_div<=menu_div+1'b1;
  wire menu_pixel_ce=menu_div==0;
  wire ui_reset_meta,ui_eep_loading_avr,ui_bound_avr;
  reg ui_reset_avr=1;
  // Pocket may query NV length after Stop, when the menu controller resets.
  // Keep the successfully bound save valid until a fresh game load starts.
  reg eeprom_valid=0;
  always @(posedge clk_74a)begin
    if(!pll_core_locked || ui_new)eeprom_valid<=0;
    else if(ui_bound)eeprom_valid<=1;
  end
  synch_3 s_menu_reset(ui_reset,ui_reset_meta,clk_avr_16);
  // Native AVR timers use locally gated rising clocks. Change their reset
  // halfway between AVR edges, giving those gates a full half-cycle margin.
  always @(negedge clk_avr_16)ui_reset_avr<=ui_reset_meta;
  synch_3 s_eep_loading(ui_loading || ui_settle!=0,ui_eep_loading_avr,clk_avr_16);
  synch_3 s_eep_bound(ui_bound,ui_bound_avr,clk_avr_16);
  // Reset the slow-domain byte counter with a toggle, not a one-cycle pulse.
  reg load_token=0;
  always @(posedge clk_74a)if(ui_new)load_token<=~load_token;
  wire load_token_avr;
  synch_3 s_load_token(load_token,load_token_avr,clk_avr_16);
  reg load_seen=0,eep_fault_avr=0;
  reg [10:0] eep_written_avr=0;
  reg [10:0] eep_written_meta=0,eep_written=0;
  wire eep_fault;
  synch_3 s_eep_fault(eep_fault_avr,eep_fault,clk_74a);
  always @(posedge clk_74a)begin eep_written_meta<=eep_written_avr;eep_written<=eep_written_meta;end
  always @(posedge clk_avr_16)begin
    if(load_token_avr!=load_seen)begin load_seen<=load_token_avr;eep_written_avr<=0;eep_fault_avr<=0;end
    else if(eeprom_wr && ui_eep_loading_avr)begin
      if(eep_written_avr>=1024 || eeprom_addr_in!=eep_written_avr[9:0])eep_fault_avr<=1;
      if(eep_written_avr<1024)eep_written_avr<=eep_written_avr+1'b1;
    end
  end
  wire [23:0] ard_error_rgb;
  ard_error_pixels error_pixels(.clk(clk_video_1_25),.de(cf_de),.hs(cf_hs),.vs(cf_vs),.skip(cf_skip),.rgb(ard_error_rgb));
'''
    s=replace(s,'endmodule',insertion+'\nendmodule');top.write_text(s,encoding='utf8',newline='\n')
    bridge=dest/'core_bridge_cmd.v'
    bridge.write_text(base.target_bridge(bridge.read_text()),encoding='utf8',newline='\n')
    parser=dest/'rtl/rom_loader.v'
    parser.write_text(replace(parser.read_text(),'      hex_nibble_index <= 0;\n      has_digit_high <= 0;',
        '      write_en <= 0;\n      hex_nibble_index <= 0;\n      has_digit_high <= 0;'),encoding='utf8',newline='\n')
    # The upstream four-byte FIFO cannot hold one full-speed EEPROM transfer
    # into the 16MHz domain. Reserve enough for the entire 1KiB save, retaining
    # the original byte writer and its MIT notice. Drain/count gates CPU release.
    ee=(dest/'rtl/data_loader.sv').read_text().replace('module data_loader #','module ard_eeprom_loader #',1)
    ee=replace(ee,'dcfifo_component.lpm_numwords = 4,','dcfifo_component.lpm_numwords = 2048,')
    ee=replace(ee,'dcfifo_component.lpm_widthu = 2,','dcfifo_component.lpm_widthu = 11,')
    ee=replace(ee,'dcfifo_component.use_eab = "OFF",','dcfifo_component.use_eab = "ON",')
    ee=ee.replace('overflow_checking = "OFF"','overflow_checking = "ON"')
    (dest/'ard_eeprom_loader.sv').write_text(ee,encoding='utf8',newline='\n')
    # Observe the exact native write transaction, including CPU erase/write
    # modes and host restores. No instruction, register or EEPROM rule changes.
    native=dest/'rtl/avr/atmega-eep.v';ee=native.read_text()
    ee=replace(ee,'\toutput reg content_modifyed_o,','\toutput wire eep_commit_o,\n\toutput wire [$clog2(EEP_SIZE)-1:0] eep_commit_addr_o,\n\toutput wire [7:0] eep_commit_data_o,\n\toutput reg content_modifyed_o,')
    ee=replace(ee,'assign int_o =', '''assign eep_commit_o=eep_wr | ext_eep_wr;
assign eep_commit_addr_o=eep_addr;
assign eep_commit_data_o=ext_eep_data_en_i ? ext_eep_data_i : ~dat_to_write;
assign int_o =''')
    native.write_text(ee,encoding='utf8',newline='\n')
    wrapper=dest/'rtl/avr/atmega32u4_arduboy.v';ee=wrapper.read_text()
    ee=replace(ee,'\tinput ext_eep_data_en_i,','\tinput ext_eep_data_en_i,\n\toutput wire eep_commit_o,\n\toutput wire [9:0] eep_commit_addr_o,\n\toutput wire [7:0] eep_commit_data_o,')
    ee=replace(ee,'\t.content_modifyed_o(eep_content_modifyed),','\t.eep_commit_o(eep_commit_o),.eep_commit_addr_o(eep_commit_addr_o),.eep_commit_data_o(eep_commit_data_o),\n\t.content_modifyed_o(eep_content_modifyed),')
    ee=replace(ee,'assign ext_eep_data_o = 0;','assign ext_eep_data_o = 0;\nassign eep_commit_o=0;assign eep_commit_addr_o=0;assign eep_commit_data_o=0;')
    wrapper.write_text(ee,encoding='utf8',newline='\n')
    shutil.copy2(HERE/'eeprom_shadow.sv',dest/'eeprom_shadow.sv')
    shutil.copy2(HERE/'audio.sv',dest/'audio.sv')
    # floor(x/6) == (x*683)>>12 for every 10-bit unsigned x. This replaces
    # the upstream deep combinational divider without delaying any pixel or
    # changing its 6x OLED scale. Keep multiplication in available DSP blocks.
    native_video=dest/'rtl/video.sv';v=native_video.read_text()
    v=replace(v,'.raster_x_i(current_h / 6),','.raster_x_i({5\'d0,scaled_h[19:12]}),')
    v=replace(v,'.raster_y_i(current_v / 6),','.raster_y_i({5\'d0,scaled_v[19:12]}),')
    v=replace(v,'  wire [9:0] current_v;', '''  wire [9:0] current_v;
  (* multstyle = "dsp" *) wire [19:0] scaled_h = current_h * 10'd683;
  (* multstyle = "dsp" *) wire [19:0] scaled_v = current_v * 10'd683;''')
    native_video.write_text(v,encoding='utf8',newline='\n')
    (dest/'arduboy_menu.sv').write_text(controller(),encoding='utf8',newline='\n')
    target=(ROOT/'experiments/sega_coverflow/target_adapter.sv').read_text()
    (dest/'sega_menu_target.sv').write_text(target.replace("32'hF3000000","32'hF4000000"),encoding='utf8',newline='\n')
    error=(ROOT/'experiments/supervision_coverflow/error_pixels.sv').read_text().replace('sv_error','ard_error')
    (dest/'error_pixels.sv').write_text(error,encoding='utf8',newline='\n')
    sys.path.insert(0,str(ROOT/'experiments/coverflow_shared'))
    shared_builder=load('ard_shared_psram',ROOT/'experiments/coverflow_shared/prepare_psram.py')
    shared=shared_builder.build(out/'coverflow-generated',gba_source)
    files=['coverflow_geometry.sv','coverflow_psram_view.sv','coverflow_line_fetch16.sv','coverflow_psram.sv',
        'coverflow_psram_cache.sv','coverflow_dpram_ce.v','picker_dpram.v']
    for name in files:shutil.copy2(shared/name,dest/name)
    shutil.copy2(shared/'font_cn.hex',project/'font_cn.hex')
    sys.path.insert(0,str(ROOT/'tools'));import build_library as art
    columns=[0]*320
    for caption,y in [('读取失败',0),('按 A 重试',16)]:
        width,raw,clipped,missing=art.columns(caption,art.font())
        if clipped or missing:raise ValueError('Error title glyphs missing')
        for i,n in enumerate(struct.unpack('<512H',raw)[:width]):columns[(320-width)//2+i]|=n<<y
    (project/'ard_error.hex').write_text(''.join(f'{n:08x}\n' for n in columns),encoding='ascii')
    qsf=project/'ap_core.qsf'
    settings='\n'.join(line for line in qsf.read_text().splitlines() if not any(k in line for k in
        ['ENABLE_SIGNALTAP','USE_SIGNALTAP_FILE','SIGNALTAP_FILE','NUM_PARALLEL_PROCESSORS','SLD_','_SLD_','auto_signaltap']))
    settings=replace(settings,'set_global_assignment -name FITTER_EFFORT "AUTO FIT"',
        'set_global_assignment -name FITTER_EFFORT "STANDARD FIT"')
    settings+='\nset_global_assignment -name NUM_PARALLEL_PROCESSORS 4\nset_global_assignment -name ENABLE_SIGNALTAP OFF\n'
    for name in files+['arduboy_menu.sv','sega_menu_target.sv','error_pixels.sv','ard_eeprom_loader.sv','eeprom_shadow.sv','audio.sv']:
        kind='SYSTEMVERILOG_FILE' if name.endswith('.sv') else 'VERILOG_FILE'
        settings+=f'set_global_assignment -name {kind} core/{name}\n'
    qsf.write_text(settings,encoding='utf8',newline='\n')
    manifest={'source_repo':REPO,'source_commit':COMMIT,'archive_sha256':ARCHIVE_SHA,'namespace':NAMESPACE,
        'video':{'physical_mhz':46.476188,'pixel_enable':'1/8','menu_total':[374,300],'menu_active':[320,288],
            'menu_hz':46476188/8/374/300,'game_scaler_unchanged':True},
        'save_support':'1024-byte native EEPROM, per-ROM namespace. Original global save is untouched.',
        'inputs':{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}}
    (out/'ard-preparation.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['archive','out','gba-source']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();print(prepare(a.archive,a.out,a.gba_source))
