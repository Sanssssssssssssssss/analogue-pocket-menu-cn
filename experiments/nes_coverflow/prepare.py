#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reuse native NES launch/save hooks with the accepted shared CoverFlow UI."""
import argparse,importlib.util,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


base=load('nes_base',ROOT/'experiments/nes_menu/prepare_build.py')
gba=load('gba_coverflow_adapter',ROOT/'experiments/gba_coverflow/prepare.py')
replace=base.replace


def controller():
    s=gba.controller(base.controller(),exit_paths=2)
    # Offsets 16/20 remain reserved for inherited ROM offset/config fields.
    s=replace(s,'4:cf_title_width<=','6:cf_title_width<=')
    s=replace(s,'5:cf_subtitle_width<=','7:cf_subtitle_width<=')
    s=replace(s,'input wire cf_want_art,cf_anim,cf_frame_tick,cf_mem_idle,cf_fetch_fault,',
        '''input wire cf_want_art,cf_anim,cf_frame_tick,cf_mem_idle,cf_fetch_fault,cf_upload_ready,
    input wire [2:0] cf_wanted_slot,
    output reg [2:0] cf_loaded_slot=0,
    output reg cf_art_begin=0,''')
    s=replace(s,'cf_go<=0;cf_commit<=0;cf_invalidate<=0;',
        'cf_go<=0;cf_commit<=0;cf_invalidate<=0;cf_art_begin<=0;')
    s=replace(s,'cf_art_game<=cf_wanted_game;cf_chunk<=0;state<=CF_ART_REQ;',
        'cf_art_game<=cf_wanted_game;cf_loaded_slot<=cf_wanted_slot;cf_art_begin<=1;cf_chunk<=0;state<=CF_ART_REQ;')
    s=replace(s,"32'h12800000+({25'd0,cf_art_game[6:0]}<<16)+cf_chunk_offset,",
        "32'h42000000+({29'd0,cf_loaded_slot}<<16)+cf_chunk_offset,")
    s=replace(s,'CF_ART_DRAIN:if(timer>=SETTLE_CYCLES && io_idle)begin',
        'CF_ART_DRAIN:if(timer>=SETTLE_CYCLES && io_idle && cf_upload_ready)begin')
    return s


def prepare(archive,out):
    out=base.prepare(archive,out)
    dest=out/'target/pocket';top=dest/'core_top.v'
    (dest/'nes_menu.sv').write_text(controller(),encoding='utf8',newline='\n')
    sys.path.insert(0,str(ROOT/'experiments/coverflow_shared'))
    from prepare_assoc import build
    shared=build(ROOT/'.work/coverflow-delivery'/('assoc-'+out.name))
    names=['coverflow_geometry.sv','coverflow_assoc_view.sv','coverflow_assoc_cache.sv',
        'coverflow_line_fetch.sv','coverflow_dpram_ce.v','picker_dpram.v']
    for name in names:shutil.copy2(shared/name,dest/name)
    shutil.copy2(shared/'font_cn.hex',out/'projects/font_cn.hex')
    shutil.copy2(HERE/'art_ram.sv',dest/'nes_coverflow_art_ram.sv')
    s=top.read_text(encoding='utf8')
    s=replace(s,'  nes_menu menu (',(HERE/'top_insert.sv').read_text(encoding='utf8')+'\n  nes_menu menu (')
    s=replace(s,'  assign video_rgb_clock = clk_video_5_37;',
        "  assign video_skip=1'b0;\n  assign video_rgb_clock = clk_video_5_37;")
    s=replace(s,'.frame_ack(ui_ack_b)', '''.cf_want_art(cf_want),.cf_wanted_game(cf_wanted),.cf_wanted_slot(cf_wanted_slot),
      .cf_anim(cf_anim),.cf_frame_tick(cf_tick),.cf_mem_idle(cf_idle),.cf_fetch_fault(cf_fault),
      .cf_upload_ready(cf_uploaded),.cf_level(cf_level),.cf_title_level(cf_title_level),
      .cf_menu(cf_menu),.cf_go(cf_go),.cf_direction(cf_direction),.cf_invalidate(cf_invalidate),.cf_commit(cf_commit),
      .cf_generation(cf_generation),.cf_loaded_game(cf_loaded),.cf_loaded_slot(cf_loaded_slot),.cf_art_begin(cf_art_begin),
      .cf_count(cf_count),.cf_level_target(cf_target),.cf_title_target(cf_title_target),
      .cf_title_width(cf_width),.cf_subtitle_width(cf_subwidth),.frame_ack(ui_ack_b)''')
    s=replace(s,'.visible(ui_visible_b)', '.visible(cf_menu ? cf_level!=0:ui_visible_b)')
    for port in ('de','hs','vs','rgb'):
        s=replace(s,f'assign video_{port} = ui_video_{port};',f'assign video_{port} = cf_video_owner ? cf_output_{port}:ui_video_{port};')
    top.write_text(s,encoding='utf8',newline='\n')
    with (dest/'core.qip').open('a',encoding='utf8') as f:
        for name in names+['nes_coverflow_art_ram.sv']:
            f.write('set_global_assignment -name '+('SYSTEMVERILOG_FILE' if name.endswith('.sv') else 'VERILOG_FILE')+' [file join $::quartus(qip_path) "'+name+'"]\n')
    proof=json.loads((shared/'view-source.json').read_text())
    proof.update({'scope':'NES native core + five independent BRAM cover slots; game SDRAM and inherited clocks retained',
        'menu_format':'GBAF2/NES; widths at 24/28, ROM fields unchanged',
        'menu_hz':5369318/(374*300),'game_changes':'Prior isolated pause/launch/save adapter only; no game CPU emulation'})
    (out/'coverflow-preparation.json').write_text(json.dumps(proof,indent=2)+'\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();print(prepare(a.archive,a.out))
