#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native Sega lifecycle, shared CoverFlow, optional version-bound cheat payload."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


base=load('sega_nes_base',ROOT/'experiments/nes_menu/prepare_build.py')
cf=load('sega_cf_base',ROOT/'experiments/gba_coverflow/prepare.py')
replace=base.replace
PROFILES={'gg':('ggclab',1,0x10000000,0),'sms':('smslab',4,0x30000000,1),'sg1000':('sgclab',5,0x60000000,2)}


def controller(platform):
    namespace,slot,address,mode=PROFILES[platform]
    s=cf.controller(base.controller(namespace,32768,'sega_menu'),exit_paths=2)
    s=replace(s,'input wire [31:0] save_capacity,', '''input wire [31:0] save_capacity,
    input wire cf_upload_ready,cheat_payload_ready,cheat_parse_fault,
    output reg cheat_loading=0,cheat_armed=0,''')
    s=replace(s,'4:cf_title_width<=','6:cf_title_width<=')
    s=replace(s,'5:cf_subtitle_width<=','7:cf_subtitle_width<=')
    s=replace(s,'reg [31:0] atlas_stride=0;', '''reg [31:0] atlas_stride=0;
    reg [31:0] cheat_bytes=0;
    localparam CHEAT_BEGIN=53,CHEAT_OPENED=54,CHEAT_READ=55,CHEAT_DRAIN=56,CHEAT_FINISH=57;''')
    s=replace(s,'0:entry_magic<=normalized;1:entry_flags<=normalized;2:rom_bytes<=normalized;',
        '0:entry_magic<=normalized;1:entry_flags<=normalized;2:rom_bytes<=normalized;4:cheat_bytes<=normalized;')
    s=replace(s,'cf_invalidate<=0;cf_commit<=0;cf_go<=0;cf_generation<=0;',
        'cf_invalidate<=0;cf_commit<=0;cf_go<=0;cf_generation<=0;cheat_loading<=0;cheat_armed<=0;')
    s=replace(s,'cf_title_width>500 || cf_subtitle_width>300',
        'cf_title_width>500 || cf_subtitle_width>300 || cheat_bytes>65536 || cheat_bytes[1:0]!=0')
    s=replace(s,'rom_bytes>33554432','rom_bytes>4194304')
    s=replace(s,'command(1,0,0,PARAM,0,ROM_OPENED)',f'command(1,{slot},0,PARAM,0,ROM_OPENED)')
    s=replace(s,"command(0,0,0,32'h10000000,rom_bytes,ROM_READ)",f"command(0,{slot},0,32'h{address:08x},rom_bytes,ROM_READ)")
    s=s.replace('command(1,10,','command(1,2,').replace('command(0,10,','command(0,2,').replace('command(2,10,','command(2,2,').replace('command(3,10,','command(3,2,')
    s=replace(s,"32'h50000000+frame_sent","32'h80000000+frame_sent")
    s=replace(s,"32'h12800000+({25'd0,cf_art_game[6:0]}<<16)+cf_chunk_offset,",
        "32'h42000000+({25'd0,cf_art_game[6:0]}<<16)+cf_chunk_offset,")
    s=replace(s,'CF_ART_DRAIN:if(timer>=SETTLE_CYCLES && io_idle)begin',
        'CF_ART_DRAIN:if(timer>=SETTLE_CYCLES && io_idle && cf_upload_ready)begin')
    # The unused RTC path becomes a strictly confined cheat path, still bound
    # to the same 20-digit ROM identity. No file is read when cheat_bytes is 0.
    prefix=('/Assets/'+namespace+'/cheat/').encode();assert len(prefix)==21
    function='    function automatic [7:0] cheat_prefix(input [4:0] n);\n        case(n)\n'
    for i,b in enumerate(prefix):function+=f"            {i}:cheat_prefix=8'h{b:02x};\n"
    function+="            default:cheat_prefix=0;\n        endcase\n    endfunction\n"
    s=replace(s,'    function automatic path_byte_ok',function+'    function automatic path_byte_ok')
    s=replace(s,'path_byte_ok=c==save_prefix(n[4:0]);','path_byte_ok=c==(rtc ? cheat_prefix(n[4:0]):save_prefix(n[4:0]));')
    for n,letter in [(42,'c'),(43,'h'),(44,'t')]:
        previous={42:'r',43:'t',44:'c'}[n]
        s=replace(s,f'{n}:path_byte_ok=c==(rtc ? "{previous}"',f'{n}:path_byte_ok=c==(rtc ? "{letter}"')
    s=replace(s,'else begin cf_menu<=0;menu_reset<=1;menu_pause<=0;game_bound<=0;timer<=0;state<=ROM_START;end',
        'else begin cheat_loading<=0;cheat_armed<=0;cf_menu<=0;menu_reset<=1;menu_pause<=0;game_bound<=0;timer<=0;state<=ROM_START;end')
    s=replace(s,'game_bound<=1;menu_reset<=0;menu_owned<=0;menu_pause<=0;menu_show<=0;state<=RUN;',
        '''game_bound<=1;menu_reset<=0;menu_show<=0;timer<=0;
                    if(cheat_bytes==0)begin menu_owned<=0;menu_pause<=0;state<=RUN;end
                    else begin menu_owned<=1;menu_pause<=1;state<=CHEAT_BEGIN;end''')
    s=replace(s,'            RUN:if(combo', '''            CHEAT_BEGIN:if(io_idle)begin
                    path_select<=2;root_path<=0;open_flags<=0;open_size<=0;command(1,3,0,PARAM,0,CHEAT_OPENED);
                end else if(timer>=TIMEOUT)fail(8'h80);
            CHEAT_OPENED:if(result!=0)fail(8'h81);else begin
                    cheat_loading<=1;command(0,3,0,32'h50000000,cheat_bytes,CHEAT_READ);
                end
            CHEAT_READ:if(result!=0)begin cheat_loading<=0;fail(8'h82);end
                else begin timer<=0;state<=CHEAT_DRAIN;end
            CHEAT_DRAIN:if(timer>=SETTLE_CYCLES)begin cheat_loading<=0;timer<=0;state<=CHEAT_FINISH;end
            CHEAT_FINISH:if(timer>=SETTLE_CYCLES)begin
                    if(cheat_parse_fault || !cheat_payload_ready)fail(8'h83);
                    else begin cheat_armed<=1;menu_pause<=0;menu_owned<=0;state<=RUN;end
                end
            RUN:if(combo''')
    return s
