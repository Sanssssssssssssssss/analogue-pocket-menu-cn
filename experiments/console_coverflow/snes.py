#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Connect CoverFlow to the pinned standard NTSC SFC prototype."""

import argparse
import re
import shutil
import sys
from pathlib import Path

from prepare import EXPERIMENTS, ROOT, gba, load, replace

SFC = load('console_sfc', EXPERIMENTS/'snes_menu/prepare_build.py')
GBA = EXPERIMENTS/'gba_coverflow'


def retime_memory(text):
    # The byte enables already select the write lane. Replicating the byte
    # removes the DSP address adder from the write-data path to CellRAM.
    a=text.index('  wire [15:0] wram_data_in =')
    b=text.index('  wire [15:0] wram_data_out;',a)
    text=text[:a]+'''  wire wram_write_request = ~WRAM_CE_N & ~WRAM_WE_N;
  reg [25:0] wram_write_sys,wram_write_mem;
  always @(negedge clk_sys) wram_write_sys <= {WRAM_ADDR,WRAM_D,wram_write_request};
  always @(negedge clk_mem_85_9) wram_write_mem <= wram_write_sys;
  wire wram_cpu_write = wram_write_request && wram_write_mem[0] && !clearing_ram;
  wire [16:0] wram_bus_addr = wram_cpu_write ? wram_write_mem[25:9] : psram_wram_addr;
  wire [7:0] wram_data = clearing_ram ? wram_fill_data : wram_write_mem[8:1];
  wire [15:0] wram_data_in = {wram_data, wram_data};
'''+text[b:]
    # Reads retain the native request time. The delayed write bundle can
    # start only while the CPU's original write window is still active.
    text=replace(text,'.addr(psram_wram_addr[16:1])','.addr(wram_bus_addr[16:1])')
    text=replace(text,".write_en(clearing_ram ? 1'b1 : ~WRAM_CE_N & ~WRAM_WE_N)",'.write_en(clearing_ram || wram_cpu_write)')
    text=replace(text,'.write_high_byte(psram_wram_addr[0])','.write_high_byte(wram_bus_addr[0])')
    text=replace(text,'.write_low_byte(~psram_wram_addr[0])','.write_low_byte(~wram_bus_addr[0])')
    text=replace(text,"psram_aram_addr[0] ? {aram_data, 8'h0} : {8'h0, aram_data}",'{aram_data, aram_data}')
    # CPU and DSP consume memory on enabled rising edges. The falling edges
    # of the 4:1 clocks leave a half-fast-cycle margin at the clock boundary.
    text=replace(text,'  wire [15:0] ROM_Q;', '''  reg [15:0] ROM_Q;
  wire [15:0] rom_memory_data;
  reg [15:0] rom_return;
  always @(negedge clk_mem) rom_return <= rom_memory_data;
  always @(negedge clk_sys) ROM_Q <= rom_return;''')
    text=replace(text,'.dout0(ROM_Q)', '.dout0(rom_memory_data)')
    for port,lower,wire in [('WRAM','wram','wram_data_out'),('ARAM','aram','aram_16_out')]:
        text=replace(text,f'  wire [7:0] {port}_Q, {port}_D;',f'  reg [7:0] {port}_Q;\n  wire [7:0] {port}_D;')
        text=replace(text,f'  assign {port}_Q = psram_{lower}_addr[0] ? {wire}[15:8] : {wire}[7:0];',
                     f'''  reg [15:0] {lower}_return;
  always @(negedge clk_mem_85_9) {lower}_return <= {wire};
  always @(negedge clk_sys) {port}_Q <= psram_{lower}_addr[0] ? {lower}_return[15:8] : {lower}_return[7:0];''')
    # Preserve the address, byte enables and data of every audio RAM request.
    text=replace(text,'  wire [15:0] aram_16_data = {aram_data, aram_data};', '''  wire aram_write = clearing_ram | (~ARAM_CE_N & ~ARAM_WE_N);
  wire aram_read = ~aram_write & ~ARAM_CE_N & ~ARAM_OE_N;
  reg [25:0] aram_request_sys,aram_request_mem;
  always @(negedge clk_sys)
    aram_request_sys <= {psram_aram_addr,aram_write ? aram_data : 8'd0,aram_write,aram_read};
  always @(negedge clk_mem_85_9) aram_request_mem <= aram_request_sys;
  wire [15:0] aram_address = aram_request_mem[25:10];
  wire [7:0] aram_write_byte = aram_request_mem[9:2];
  // One transfer per audio request leaves a complete read window for the
  // following DSP step, even if read enable stays high across both steps.
  reg [25:0] aram_issued=0;
  wire aram_busy;
  wire aram_new_request = aram_request_mem != aram_issued;
  always @(posedge clk_mem_85_9)
    if (!aram_busy && aram_new_request) aram_issued <= aram_request_mem;''')
    text=replace(text,'.addr(psram_aram_addr[15:1])','.addr(aram_address[15:1])')
    text=replace(text,".write_en(clearing_ram ? 1'b1 : ~ARAM_CE_N & ~ARAM_WE_N)",'.write_en(aram_request_mem[1] && aram_new_request)')
    text=replace(text,'.data_in(aram_16_data)','.data_in({aram_write_byte,aram_write_byte})')
    text=replace(text,'.write_high_byte(psram_aram_addr[0])','.write_high_byte(aram_address[0])')
    text=replace(text,'.write_low_byte(~psram_aram_addr[0])','.write_low_byte(~aram_address[0])')
    text=replace(text,'.read_en (~ARAM_CE_N & ~ARAM_OE_N)','.read_en(aram_request_mem[0] && aram_new_request),\n      .busy(aram_busy)')
    return text


def prepare(archive, out):
    out = SFC.prepare(archive,out)
    memory = out/'rtl/mister_top/SNES.sv'
    memory.write_text(retime_memory(memory.read_text(encoding='utf8')),encoding='utf8',newline='\n')
    dest = out/'target/pocket'
    top = dest/'core_top.sv'
    text = top.read_text(encoding='utf8')
    for signal,value in [('a',"'h0"),('dq',"{16{1'bZ}}"),('oe_n','1'),('we_n','1'),('ub_n','1'),('lb_n','1')]:
        pattern = rf'  assign sram_{signal}\s*= {re.escape(value)};\n'
        text,count = re.subn(pattern,'',text)
        if count!=1:
            raise ValueError('SFC dedicated SRAM no longer idle: '+signal)

    # SFC uses both CellRAM chips. Use only the otherwise idle asynchronous SRAM.
    insertion=(GBA/'top_sram.sv').read_text(encoding='utf8')
    start=insertion.index('reg [2:0] cf_pixel_div=0;')
    end=insertion.index('wire cf_text_we',start)
    # The upstream clk_video_5_37 signal is actually 10.738635 MHz (PLL outclk2).
    # A half-rate enable keeps 374x300 menu frames at 47.855 Hz; the renderer
    # asserts hr_skip on the held pixel cycles. Native game timing is unchanged.
    insertion=insertion[:start]+'''reg cf_pixel_div=0;
always @(posedge clk_vid)cf_pixel_div<=~cf_pixel_div;
wire cf_pixel_ce=cf_pixel_div;
'''+insertion[end:]
    insertion=insertion.replace('target_dataslot_read','ui_read').replace('target_dataslot_bridgeaddr','ui_address')
    insertion='''  wire clk_sys=clk_mem_85_9,clk_vid=clk_video_5_37;
  wire cf_game_vs=game_vs,cf_game_hs=game_hs,cf_game_de=de,cf_game_skip=1'b0;
  wire [23:0] cf_game_rgb=rgb;
''' + insertion
    video=(GBA/'video_mux.sv').read_text(encoding='utf8')
    video=video[video.index('reg cf_video_owner=1;'):]
    video=video.replace('cf_menu && !ui_fault','cf_menu || ui_fault').replace("24'h002000","24'h008000")
    text=replace(text,'  snes_menu menu (',insertion+video+'\n  snes_menu menu (')
    text=replace(text,'.visible(ui_visible_b),', '''.visible(cf_menu && cf_level!=0),
      .cf_want_art(cf_want),.cf_wanted_game(cf_wanted),.cf_anim(cf_anim),.cf_frame_tick(cf_tick),
      .cf_mem_idle(cf_mem_idle),.cf_fetch_fault(cf_fetch_fault),.cf_upload_ready(cf_uploaded),
      .cf_level(cf_level),.cf_title_level(cf_title_level),.cf_wanted_slot(cf_wanted_slot),.cf_loaded_slot(cf_loaded_slot),
      .cf_menu(cf_menu),.cf_go(cf_go),.cf_direction(cf_direction),.cf_invalidate(cf_invalidate),.cf_commit(cf_commit),
      .cf_generation(cf_generation),.cf_loaded_game(cf_loaded),.cf_count(cf_count),.cf_level_target(cf_target),
      .cf_title_target(cf_title_target),.cf_title_width(cf_width),.cf_subtitle_width(cf_subwidth),''')
    text=replace(text,'.frame_ack(ui_ack_b),.frame_started(ui_started_b),\n      .frame_valid(ui_valid_b),.frame_fault(ui_pixel_fault_b),',
                 ".frame_ack(1'b0),.frame_started(1'b0),\n      .frame_valid(1'b0),.frame_fault(1'b0),")
    a,b=text.index('  gba_menu_pixels menu_pixels'),text.index('  // bridge data slot access')
    text=text[:a]+text[b:]
    text=replace(text,'  assign video_rgb = ui_video_rgb;\n  assign video_de = ui_video_de;\n  assign video_hs=ui_video_hs;assign video_vs=ui_video_vs;','')
    text=replace(text,'if(!reset_n)begin ui_loading<=0;ui_settle<=0;end','if(!reset_n || ui_fault)begin ui_loading<=0;ui_settle<=0;end')
    top.write_text(text,encoding='utf8',newline='\n')

    ctrl=gba.controller(SFC.controller(),exit_paths=2,cellram=True,associative=True)
    ctrl=replace(ctrl,'4:cf_title_width<=','6:cf_title_width<=')
    ctrl=replace(ctrl,'5:cf_subtitle_width<=','7:cf_subtitle_width<=')
    (dest/'snes_menu.sv').write_text(ctrl,encoding='utf8',newline='\n')
    sys.path.insert(0,str(EXPERIMENTS/'coverflow_shared'))
    from prepare_assoc import build
    shared=build(ROOT/'.work/coverflow-delivery'/('console-'+out.name))
    files=['coverflow_geometry.sv','coverflow_assoc_view.sv','coverflow_assoc_cache.sv','coverflow_line_fetch.sv',
           'coverflow_dpram_ce.v','picker_dpram.v']
    for name in files:
        shutil.copy2(shared/name,dest/name)
    shutil.copy2(GBA/'sram_cache.sv',dest/'coverflow_sram_cache.sv')
    shutil.copy2(shared/'font_cn.hex',out/'projects/font_cn.hex')
    with (dest/'core.qip').open('a',encoding='utf8',newline='\n') as qip:
        for name in [*files,'coverflow_sram_cache.sv']:
            kind='SYSTEMVERILOG_FILE' if name.endswith('.sv') else 'VERILOG_FILE'
            qip.write(f'set_global_assignment -name {kind} [file join $::quartus(qip_path) "{name}"]\n')
    # The same read cycle has additional settling margin at SFC's 85.9 MHz.
    with (dest/'core_constraints.sdc').open('a',encoding='utf8',newline='\n') as sdc:
        sdc.write(gba.SRAM_SDC.replace('sys_pll_i|general[0]', 'altera_pll_i|general[0]'))
    return out


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--archive',required=True,type=Path)
    cli.add_argument('--out',required=True,type=Path)
    args=cli.parse_args()
    print(prepare(args.archive,args.out))
