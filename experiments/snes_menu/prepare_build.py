#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare a standard NTSC SNES-only visual menu; original special-chip cores remain separate."""
import argparse,importlib.util,json,re,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('nes_prepare',ROOT/'experiments/nes_menu/prepare_build.py')
nes=importlib.util.module_from_spec(spec);spec.loader.exec_module(nes)
replace=nes.replace
ARCHIVE_SHA='0a1151ccb8d1a53538d6ea121e09d0ae5059cecfb93d9ee68659944982743c94'

def controller():
    s=nes.controller('snescn',131072,'snes_menu')
    s=replace(s,'output reg [7:0] state=0,','output reg [31:0] rom_config=0,rom_offset=0,\n    output reg [7:0] state=0,')
    s=replace(s,'2:rom_bytes<=normalized;', '2:rom_bytes<=normalized;4:rom_offset<=normalized;5:rom_config<=normalized;')
    s=replace(s,"else if(rom_bytes<192 || rom_bytes>33554432 || rom_bytes[1:0]!=0)fail(8'h12);",
        "else if(rom_bytes<32768 || rom_bytes>16777216 || rom_bytes[1:0]!=0 ||\n                    (rom_offset!=0 && rom_offset!=512) || rom_config[31:16]!=0 ||\n                    rom_config[7:0]>2 || rom_config[15:12]>7)fail(8'h12);")
    s=replace(s,"command(0,0,0,32'h10000000,rom_bytes,ROM_READ)","command(0,0,rom_offset,32'h10000000,rom_bytes,ROM_READ)")
    s=replace(s,'if(save_capacity!=131072)',
        'if(save_capacity>131072 || (save_capacity & (save_capacity-1))!=0 || (save_capacity!=0 && save_capacity<2048))')
    s=replace(s,'else begin save_bytes<=save_capacity;state<=SAVE_OPEN;end',
        'else begin save_bytes<=save_capacity;state<=save_capacity==0 ? LOAD_FINISH : SAVE_OPEN;end')
    # First preview uses the upstream OS exit/save flow. No unverified runtime pause.
    start=s.index('            RUN:');end=s.index('            PAUSE_WAIT:',start)
    s=s[:start]+'            RUN:begin end\n'+s[end:]
    return s

def prepare(archive,out):
    out=nes.extract_source(archive,out,ARCHIVE_SHA)
    core=out/'target/pocket/core_top.sv';s=core.read_text(encoding='utf8')
    insertion=(ROOT/'experiments/nes_menu/top_insert.sv').read_text(encoding='utf8')
    insertion=insertion.replace('Pocket Lab NES','Pocket Lab SNES').replace('NES core','SNES core')
    insertion=insertion.replace('clk_ppu_21_47','clk_sys_21_48').replace('nes_menu menu','snes_menu menu')
    insertion=insertion.replace(".save_capacity(32'd262144)",".save_capacity(ui_config[15:12]==0 ? 32'd0 : 32'd1024 << ui_config[15:12])")
    insertion=insertion.replace('.game_rgb(video_rgb_reg),.game_de(video_de_reg),.game_hs(video_hs_reg),.game_vs(video_vs_reg)',
        '.game_rgb(rgb),.game_de(de),.game_hs(game_hs),.game_vs(game_vs)')
    insertion=insertion.replace('wire ui_read,ui_write,ui_open,ui_flush,ui_done;',
        'wire [31:0] ui_config,ui_rom_offset;\n  wire game_hs,game_vs;\n  wire ui_read,ui_write,ui_open,ui_flush,ui_done;')
    insertion=insertion.replace('wire ui_owned_s,ui_reset_s,ui_pause_s,ui_paused_s,ui_paused;',
        "wire ui_owned_s,ui_reset_s,ui_pause_s,ui_paused_s,ui_paused;\n  assign ui_paused_s=1'b0;")
    insertion=insertion.replace('.first_fault_code(ui_first_fault),.state(ui_state),.selected(ui_selected)',
        '.first_fault_code(ui_first_fault),.rom_config(ui_config),.rom_offset(ui_rom_offset),.state(ui_state),.selected(ui_selected)')
    s=replace(s,'  // bridge data slot access',insertion+'\n  // bridge data slot access')
    s=replace(s,"      32'hF8xxxxxx: begin", "      32'hF3xxxxxx: begin bridge_rd_data <= ui_param; end\n      32'hF8xxxxxx: begin")
    s=replace(s,'      .datatable_addr(datatable_addr),','''      .target_dataslot_read(ui_read),.target_dataslot_write(ui_write),
      .target_dataslot_flush(ui_flush),.target_dataslot_getfile(1'b0),
      .target_dataslot_openfile(ui_open),.target_dataslot_done(ui_done),.target_dataslot_err(ui_error),
      .target_dataslot_id(ui_slot),.target_dataslot_slotoffset(ui_offset),
      .target_dataslot_bridgeaddr(ui_address),.target_dataslot_length(ui_length),
      .target_buffer_param_struct(32'hF3000000),.target_buffer_resp_struct(32'd0),
      .datatable_addr(datatable_addr),''')
    s=replace(s,'          ioctl_download <= bridge_wr_data[0];','          ioctl_download <= bridge_wr_data[0];')
    # Loading/configuration is owned by the menu in this isolated core.
    s=replace(s,'    if (bridge_wr) begin', '''    if(ui_new)begin
      rom_type<=ui_config[7:0];rom_size<=ui_config[11:8];ram_size<=ui_config[15:12];PAL<=0;
    end
    if (bridge_wr) begin''')
    s=replace(s,'.ioctl_download(ioctl_download),','.ioctl_download(ui_loading),')
    s=replace(s,'.save_download(save_download_s),','.save_download(ui_loading_s),')
    s=replace(s,'  wire save_download_s;','  wire save_download_s;\n  wire ui_loading_s;\n  synch_3 menu_loading_sync(ui_loading,ui_loading_s,clk_sys_21_48);')
    s=replace(s,'.core_reset(~pll_core_locked || reset_button_s),','.core_reset(~pll_core_locked || reset_button_s || ui_reset_s),')
    s=replace(s,'datatable_addr <= 1 * 2 + 1;','datatable_addr <= 2 * 2 + 1;')
    # Original OS quit saves only a fully loaded/bound game, never menu/partial RAM.
    s=replace(s,"datatable_data <= sram_size ? 32'd1024 << sram_size : 32'h0;",
        "datatable_data <= ui_bound && sram_size ? 32'd1024 << sram_size : 32'h0;")
    start=s.index('  // Video\n');end=s.index('  sound_i2s #(',start)
    video=s[start:end]
    video=re.sub(r'\bvideo_hs\b','game_hs',video);video=re.sub(r'\bvideo_vs\b','game_vs',video)
    video=replace(video,'assign video_rgb = rgb;','assign video_rgb = ui_video_rgb;')
    video=replace(video,'assign video_de = de;','assign video_de = ui_video_de;\n  assign video_hs=ui_video_hs;assign video_vs=ui_video_vs;')
    s=s[:start]+video+s[end:]
    core.write_text(s,encoding='utf8',newline='\n')
    # The standard preview leaves the optional co-processors disabled, as in the
    # upstream 'none' preset. Library generation must reject other chip types/PAL.
    table=out/'platform/pocket/mf_datatable.v';s=table.read_text(encoding='utf8')
    s=replace(s,'altsyncram_component.init_file = "./build_id.mif",','altsyncram_component.init_file = "../platform/pocket/build_id.mif",')
    table.write_text(s,encoding='utf8',newline='\n')
    cmd=out/'target/pocket/core_bridge_cmd.v';s=cmd.read_text(encoding='utf8')
    s=replace(s,'input   wire            target_dataslot_read,','input wire target_dataslot_flush,\ninput   wire            target_dataslot_read,')
    s=replace(s,'reg             target_dataslot_read_1, target_dataslot_read_queue;',
        'reg target_dataslot_flush_1=0,target_dataslot_flush_queue=0;\n    reg             target_dataslot_read_1, target_dataslot_read_queue;')
    s=replace(s,'target_dataslot_read_1 <= target_dataslot_read;',
        'target_dataslot_flush_1<=target_dataslot_flush;\n    if(target_dataslot_flush && !target_dataslot_flush_1)target_dataslot_flush_queue<=1;\n    target_dataslot_read_1 <= target_dataslot_read;')
    s=replace(s,'end else if(target_dataslot_getfile_queue) begin',
        "end else if(target_dataslot_flush_queue) begin\n            target_dataslot_flush_queue<=0;target_0[15:0]<=16'h0188;target_20<=target_dataslot_id;\n            tstate<=TARG_ST_DATASLOTOP;\n        end else if(target_dataslot_getfile_queue) begin")
    cmd.write_text(s,encoding='utf8',newline='\n')
    dest=out/'target/pocket';(dest/'snes_menu.sv').write_text(controller(),encoding='utf8',newline='\n')
    shutil.copy2(ROOT/'experiments/gba_menu/gba_menu_pixels.sv',dest/'gba_menu_pixels.sv')
    shutil.copy2(ROOT/'experiments/nes_menu/menu_video.sv',dest/'menu_video.sv')
    with (dest/'core.qip').open('a',encoding='utf8') as f:
        for name in ['snes_menu.sv','gba_menu_pixels.sv','menu_video.sv']:
            f.write(f'\nset_global_assignment -name SYSTEMVERILOG_FILE [file join $::quartus(qip_path) "{name}"]\n')
    # This is generated from the same checked font inputs by the NES preparation.
    spec=importlib.util.spec_from_file_location('gb_lib',ROOT/'tools/build_library.py')
    gb=importlib.util.module_from_spec(spec);sys.path.insert(0,str(ROOT/'tools'));spec.loader.exec_module(gb)
    import struct
    columns=[0]*240
    for line,y in [('操作失败',0),('A 重试　B 返回',32)]:
        width,raw,_,missing=gb.columns(line,gb.font());assert not missing
        values=struct.unpack('<512H',raw)
        for i in range(width):columns[(240-width)//2+i]|=values[i]<<y
    (out/'projects/gba_menu_error.hex').write_text(''.join(f'{x:016x}\n' for x in columns))
    (out/'menu-preparation.json').write_text(json.dumps({'upstream_archive_sha256':ARCHIVE_SHA,
        'scope':'Standard NTSC SNES preview, chip_type 0/1/2 only. Original special-chip/PAL cores unchanged. OS quit/save flow; no runtime Chinese pause/return or device acceptance.'},indent=2)+'\n')
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    print(prepare(a.archive,a.out))
