#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Adapt the tested GBA lifecycle to the accepted shared CoverFlow renderer.

All edits land in a new .work tree. The accepted GB/GBC inputs, upstream source,
and earlier GBA candidates are immutable inputs.
"""
import argparse,importlib.util,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('gba_prepare',ROOT/'experiments/gba_menu/prepare_build.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
replace=base.replace

CRAM1_SDC='''
# CoverFlow's independent asynchronous CellRAM1, on the native sys clock.
# Same external latch/setup/hold budgets as CRAM0; native constraints remain.
# These FPGA-side budgets do not replace a vendor/board timing model.
set cf_cram1_clock [get_clocks {ic|mp1|mf_pllbase_inst|sys_pll_i|general[0].gpll~PLL_OUTPUT_COUNTER|divclk}]
set cf_cram1_period [get_clock_info -period $cf_cram1_clock]
set_max_delay [expr {$cf_cram1_period * 2 - 5.0}] -from $cf_cram1_clock -to [get_ports {cram1_a[*] cram1_dq[*]}]
set_max_delay [expr {$cf_cram1_period * 2 - 7.0}] -from $cf_cram1_clock -to [get_ports {cram1_ce0_n cram1_ce1_n cram1_clk cram1_cre cram1_lb_n cram1_oe_n cram1_ub_n cram1_we_n}]
set_max_delay [expr {$cf_cram1_period - 2.0}] -from $cf_cram1_clock -to [get_ports {cram1_adv_n}]
set_min_delay 0.000 -from $cf_cram1_clock -to [get_ports {cram1_a[*] cram1_dq[*] cram1_ce0_n cram1_ce1_n cram1_clk cram1_cre cram1_lb_n cram1_oe_n cram1_ub_n cram1_we_n cram1_adv_n}]
set_max_delay $cf_cram1_period -from [get_ports {cram1_dq[*] cram1_wait}] -to $cf_cram1_clock
set_min_delay 0.000 -from [get_ports {cram1_dq[*] cram1_wait}] -to $cf_cram1_clock
'''

def controller(text,exit_paths=1,cellram=False):
    text=replace(text,'// GBAF1 page reader and GBA launch/save lifecycle, clocked by the APF bridge.',
        '// GBAF2 CoverFlow adapter; inherited GBA launch, ordinary save and RTC lifecycle.')
    text=replace(text,'input wire [31:0] save_capacity,','''input wire [31:0] save_capacity,
    input wire cf_want_art,cf_anim,cf_frame_tick,cf_mem_idle,cf_fetch_fault,
    input wire [10:0] cf_wanted_game,
    input wire [3:0] cf_level,cf_title_level,
    output reg cf_menu=1,cf_go=0,cf_direction=0,cf_invalidate=0,cf_commit=0,cf_generation=0,
    output reg [10:0] cf_loaded_game=0,
    output wire [10:0] cf_count,
    output reg [3:0] cf_level_target=0,cf_title_target=0,
    output reg [8:0] cf_title_width=0,cf_subtitle_width=0,''')
    text=replace(text,'localparam [31:0] FRAME_SIZE=76800;','''localparam CF_TEXT_WAIT=47,CF_TEXT_DONE=48,CF_ART_REQ=49,CF_ART_DONE=50,CF_ART_DRAIN=51,CF_EXIT=52;
    reg [3:0] cf_pending=0;
    reg [5:0] cf_repeat=0;
    reg [1:0] cf_chunk=0;
    reg [10:0] cf_art_game=0;
    reg [7:0] cf_after_exit=ACTIVATE;
    reg [31:0] atlas_stride=0;
    assign cf_count=count[10:0];
    wire [31:0] cf_chunk_offset={16'd0,cf_chunk,14'd0};
    localparam [31:0] FRAME_SIZE=76800;''')
    text=replace(text,'3:frame_base<=normalized;4:pause_base<=normalized;',
        '3:frame_base<=normalized;4:pause_base<=normalized;5:atlas_stride<=normalized;')
    text=replace(text,'0:entry_magic<=normalized;1:entry_flags<=normalized;2:rom_bytes<=normalized;',
        '''0:entry_magic<=normalized;1:entry_flags<=normalized;2:rom_bytes<=normalized;
            4:cf_title_width<=normalized<=500 ? normalized[8:0]:9'h1FF;
            5:cf_subtitle_width<=normalized<=300 ? normalized[8:0]:9'h1FF;''')
    text=replace(text,'begin frame_offset<=offset;after_frame<=next_state;menu_owned<=1;menu_show<=0;timer<=0;state<=FRAME_BLANK;end',
        '''begin
            menu_owned<=1;timer<=0;
            if(next_state==MENU)begin cf_menu<=1;cf_title_target<=0;state<=CF_TEXT_WAIT;end
            else begin frame_offset<=offset;after_frame<=next_state;menu_show<=0;state<=FRAME_BLANK;end
        end''')
    text=replace(text,'t_read<=0;t_open<=0;t_write<=0;t_flush<=0;new_load<=0;finish_load<=0;',
        '''t_read<=0;t_open<=0;t_write<=0;t_flush<=0;new_load<=0;finish_load<=0;
        cf_go<=0;cf_commit<=0;cf_invalidate<=0;
        if(cf_menu && !game_bound)begin
            cf_pending<=cf_pending | {press[5],press[4],press[3]|press[1],press[2]|press[0]};
            if(cf_frame_tick)begin
                if(!(buttons[0]||buttons[1]||buttons[2]||buttons[3]))cf_repeat<=0;
                else if(cf_repeat<18)cf_repeat<=cf_repeat+1'b1;
                else begin
                    cf_repeat<=14;
                    if(buttons[0]||buttons[2])cf_pending[0]<=1;
                    else cf_pending[1]<=1;
                end
            end
        end else begin cf_pending<=0;cf_repeat<=0;end''')
    text=replace(text,'fault_code<=0;first_fault_code<=0;go_back<=0;root_path<=0;command_armed<=0;',
        '''fault_code<=0;first_fault_code<=0;go_back<=0;root_path<=0;command_armed<=0;
            cf_menu<=1;cf_pending<=0;cf_repeat<=0;cf_level_target<=0;cf_title_target<=0;
            cf_invalidate<=0;cf_commit<=0;cf_go<=0;cf_generation<=0;''')
    text=replace(text,'header_version!=1','header_version!=2')
    text=replace(text,"pause_base<frame_base || pause_base>32'h10000000",
        "pause_base!=frame_base+(count<<16) || atlas_stride!=65536")
    text=replace(text,'else begin selected<=0;state<=RECORD_REQ;end',
        'else begin selected<=0;cf_pending<=0;cf_invalidate<=1;cf_menu<=1;cf_level_target<=0;state<=RECORD_REQ;end')
    text=replace(text,"RECORD_REQ:command(0,100,64+({21'd0,selected}<<10),32'h60000000,1024,RECORD_CHECK);",
        "RECORD_REQ:if(cf_title_level==0)command(0,100,64+({21'd0,selected}<<10),32'h60000000,1024,RECORD_CHECK); else cf_title_target<=0;")
    text=replace(text,"entry_magic!=32'h31544E45 || entry_flags>1",
        "entry_magic!=32'h31544E45 || entry_flags>1 || cf_title_width>500 || cf_subtitle_width>300")
    start=text.index('            MENU:begin');end=text.index('            ACTIVATE:begin',start)
    text=text[:start]+'''            MENU:begin
                if(cf_fetch_fault)fail(8'h74);
                else if(!cf_anim && cf_pending[2])begin
                    cf_pending<=0;cf_level_target<=0;cf_title_target<=0;cf_after_exit<=ACTIVATE;timer<=0;state<=CF_EXIT;
                end else if(!cf_anim && cf_pending[3])begin
                    cf_pending<=0;cf_level_target<=0;cf_title_target<=0;cf_after_exit<=RECORD_REQ;timer<=0;state<=CF_EXIT;
                end else if(!cf_anim && (cf_pending[0]||cf_pending[1]))begin
                    cf_direction<=cf_pending[0];cf_go<=1;cf_title_target<=0;
                    selected<=cf_pending[0] ? (selected==0 ? count[10:0]-1'b1:selected-1'b1) : (selected+1>=count ? 11'd0:selected+1'b1);
                    cf_pending[1:0]<=0;timer<=0;state<=RECORD_REQ;
                end else if(cf_want_art && !game_bound && io_idle)begin
                    cf_art_game<=cf_wanted_game;cf_chunk<=0;state<=CF_ART_REQ;
                end
            end
            CF_TEXT_WAIT:if(cf_title_level==0)command(0,100,frame_base+({21'd0,selected}<<16)+45568,32'h71000000,2048,CF_TEXT_DONE);
                else if(timer>=TIMEOUT)fail(8'h75);
            CF_TEXT_DONE:if(result!=0)fail(8'h76);else begin
                    cf_generation<=~cf_generation;cf_title_target<=8;cf_level_target<=8;menu_show<=1;state<=MENU;
                end
            CF_ART_REQ:command(0,100,frame_base+({21'd0,cf_art_game}<<16)+cf_chunk_offset,
                32'h12800000+({25'd0,cf_art_game[6:0]}<<16)+cf_chunk_offset,
                cf_chunk==2 ? 32'd12800:32'd16384,CF_ART_DONE);
            CF_ART_DONE:if(result!=0)fail(8'h70);
                else if(cf_chunk==2)begin timer<=0;state<=CF_ART_DRAIN;end
                else begin cf_chunk<=cf_chunk+1'b1;state<=CF_ART_REQ;end
            CF_ART_DRAIN:if(timer>=SETTLE_CYCLES && io_idle)begin
                    cf_loaded_game<=cf_art_game;cf_commit<=1;state<=MENU;
                end else if(timer>=TIMEOUT)fail(8'h71);
            CF_EXIT:if(cf_level==0 && cf_mem_idle && !visible && io_idle)begin
                    menu_show<=0;
                    if(cf_after_exit==RECORD_REQ)begin selected<=count[10:0]-1'b1;go_back<=1;end
                    state<=cf_after_exit;
                end else if(timer>=TIMEOUT)fail(8'h72);
''' + text[end:]
    text=replace(text,'else begin menu_reset<=1;menu_pause<=0;game_bound<=0;timer<=0;state<=ROM_START;end',
        'else begin cf_menu<=0;menu_reset<=1;menu_pause<=0;game_bound<=0;timer<=0;state<=ROM_START;end')
    text=replace(text,'game_bound<=0;menu_reset<=1;menu_pause<=0;menu_show<=0;timer<=0;state<=RECORD_REQ;',
        'cf_menu<=1;cf_pending<=0;cf_level_target<=0;cf_title_target<=0;game_bound<=0;menu_reset<=1;menu_pause<=0;menu_show<=0;timer<=0;state<=RECORD_REQ;',exit_paths)
    text=replace(text,'HOME_OPEN:begin root_path<=1;',
        'HOME_OPEN:begin cf_menu<=1;cf_level_target<=0;cf_title_target<=0;root_path<=1;')
    # NES/Sega adapt the legacy controller too; keep their accepted output
    # unchanged while the GBA transport gains a physical-upload drain fence.
    if cellram:
        text=replace(text,'input wire cf_want_art,cf_anim,cf_frame_tick,cf_mem_idle,cf_fetch_fault,',
            'input wire cf_want_art,cf_anim,cf_frame_tick,cf_mem_idle,cf_fetch_fault,cf_upload_ready,')
        text=replace(text,"32'h12800000+({25'd0,cf_art_game[6:0]}<<16)+cf_chunk_offset,",
            "32'h42000000+({25'd0,cf_art_game[6:0]}<<16)+cf_chunk_offset,")
        text=replace(text,'CF_ART_DRAIN:if(timer>=SETTLE_CYCLES && io_idle)begin',
            'CF_ART_DRAIN:if(timer>=SETTLE_CYCLES && io_idle && cf_upload_ready)begin')
        text=replace(text,'cf_loaded_game<=cf_art_game;cf_commit<=1;state<=MENU;',
            'cf_loaded_game<=cf_art_game;cf_commit<=1;state<=53;')
        # Let need_clr invalidate the published cache miss before requesting
        # another atlas. Otherwise the just-committed cover is read twice.
        text=replace(text,'            CF_EXIT:if(cf_level==0',
            '            53:state<=MENU;\n            CF_EXIT:if(cf_level==0')
    return text

def prepare(source,out):
    out=base.prepare(source,out,True)
    core=out/'src/fpga/core';top=core/'core_top.sv'
    (core/'gba_menu.sv').write_text(controller((core/'gba_menu.sv').read_text(encoding='utf8'),cellram=True),encoding='utf8',newline='\n')
    sys.path.insert(0,str(ROOT/'experiments/coverflow_shared'))
    from prepare_psram import build as shared_prepare
    shared=shared_prepare(ROOT/'.work/coverflow-delivery'/('shared-'+out.name),source,
        fast_response=True,clock_speed=100.663296)
    files=['coverflow_geometry.sv','coverflow_psram_view.sv','coverflow_line_fetch16.sv',
        'coverflow_psram.sv','coverflow_psram_cache.sv','coverflow_dpram_ce.v','picker_dpram.v']
    for name in files:
        shutil.copy2(shared/name,core/name)
    shutil.copy2(shared/'font_cn.hex',out/'src/fpga/build/font_cn.hex')
    s=top.read_text(encoding='utf8')
    s=replace(s,'gba_menu menu (',(HERE/'top_insert.sv').read_text(encoding='utf8')+'\ngba_menu menu (')
    s=replace(s,'.frame_ack(ui_frame_ack_b)', '''.cf_want_art(cf_want),.cf_wanted_game(cf_wanted),.cf_anim(cf_anim),.cf_frame_tick(cf_tick),
    .cf_mem_idle(cf_mem_idle),.cf_fetch_fault(cf_fetch_fault),.cf_upload_ready(cf_uploaded),.cf_level(cf_level),.cf_title_level(cf_title_level),
    .cf_menu(cf_menu),.cf_go(cf_go),.cf_direction(cf_direction),.cf_invalidate(cf_invalidate),.cf_commit(cf_commit),
    .cf_generation(cf_generation),.cf_loaded_game(cf_loaded),.cf_count(cf_count),
    .cf_level_target(cf_target),.cf_title_target(cf_title_target),.cf_title_width(cf_width),.cf_subtitle_width(cf_subwidth),
    .frame_ack(ui_frame_ack_b)''')
    s=replace(s,'.visible(ui_visible_bridge)', '.visible(cf_menu ? cf_level!=0 : ui_visible_bridge)')
    # CRAM0 belongs to the native GBA/save path; only the unused CRAM1 pins
    # change ownership. No CoverFlow requests enter the game's SDRAM loader.
    idle_cram1="assign cram1_a = 'h0;\nassign cram1_dq = {16{1'bZ}};\n"+''.join(
        f'assign cram1_{name} = {value};\n' for name,value in [
            ('clk',0),('adv_n',1),('cre',0),('ce0_n',1),('ce1_n',1),
            ('oe_n',1),('we_n',1),('ub_n',1),('lb_n',1)])
    s=replace(s,idle_cram1,'// CRAM1 is owned exclusively by the CoverFlow cache.\n')
    for signal in ['rgb','de','vs','hs','skip']:
        s=replace(s,f'.video_{signal}  ( video_{signal} )' if signal=='rgb' else f'.video_{signal}   ( video_{signal} )' if signal in ['de','vs','hs'] else '.video_skip ( video_skip )',
            f'.video_{signal} ( cf_game_{signal} )')
    s=replace(s,'video_adapter video_out (',(HERE/'video_mux.sv').read_text(encoding='utf8')+'\nvideo_adapter video_out (')
    top.write_text(s,encoding='utf8',newline='\n')
    with (core/'core_constraints.sdc').open('a',encoding='utf8',newline='\n') as f:f.write(CRAM1_SDC)
    with (out/'src/fpga/build/ap_core.qsf').open('a') as f:
        for name in files:
            f.write('set_global_assignment -name '+('SYSTEMVERILOG_FILE' if name.endswith('.sv') else 'VERILOG_FILE')+' ../core/'+name+'\n')
    settings=out/'src/fpga/build/ap_core.qsf'
    settings.write_text(replace(settings.read_text(encoding='utf8'),
        'set_global_assignment -name SEED 4','set_global_assignment -name SEED 5'),encoding='utf8',newline='\n')
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sources',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    print(prepare(a.sources,a.out))
