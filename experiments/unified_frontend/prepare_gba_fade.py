#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare a separate GBA fade candidate; never reads or writes a device card."""
import argparse
from pathlib import Path
import shutil
import sys

here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parent/'gba_menu'))
from prepare_build import prepare,replace

def build(source,out):
    out=prepare(source,out,menu=True)
    video=out/'src/fpga/core/video_adapter.sv';s=video.read_text(encoding='utf8')
    s=replace(s,'input wire menu_show,menu_fault,','input wire menu_show,menu_fault,menu_active,')
    s=replace(s,'reg show_frame=0,fault_frame=0;',
              'reg show_frame=0,fault_frame=0,active_frame=1;\n    reg [2:0] active_sync=7;\n    wire [3:0] menu_level;')
    s=replace(s,'show_sync<={show_sync[1:0],menu_show};',
              'active_sync<={active_sync[1:0],menu_active};\n        show_sync<={show_sync[1:0],menu_show};')
    s=replace(s,'if(reset)begin show_frame<=0;fault_frame<=0;end',
              'if(reset)begin show_frame<=0;fault_frame<=0;active_frame<=1;end')
    s=replace(s,'else if(video_vs)begin show_frame<=show_sync[2];fault_frame<=fault_sync[2];end',
              'else if(video_vs)begin show_frame<=show_sync[2];fault_frame<=fault_sync[2];active_frame<=active_sync[2];end')
    s=replace(s,'assign menu_visible=show_frame | fault_frame;',
              'assign menu_visible=fault_frame || (active_frame ? menu_level!=0 : show_frame);')
    anchor='wire [7:0] b8 = {pixel_read[5:0],   pixel_read[5:4]};'
    s=replace(s,anchor,anchor+'''
    wire [23:0] menu_pixel;
    menu_fade transition(.clk(clk_vid),.reset(reset),.frame_tick(video_vs),
        .enabled(active_frame),.requested_visible(show_sync[2]),.pixel({r8,g8,b8}),
        .level(menu_level),.blank(),.gained_pixel(menu_pixel));
''')
    s=replace(s,"show_frame ? {r8,g8,b8} : 24'd0;",
              "active_frame ? menu_pixel : show_frame ? {r8,g8,b8} : 24'd0;")
    video.write_text(s,encoding='utf8',newline='\n')
    top=out/'src/fpga/core/core_top.sv';s=top.read_text(encoding='utf8')
    s=replace(s,'.menu_fault ( ui_fault ),','.menu_fault ( ui_fault ),\n    .menu_active ( ui_owned ),')
    top.write_text(s,encoding='utf8',newline='\n')
    shutil.copy2(here/'menu_fade.sv',out/'src/fpga/core/menu_fade.sv')
    with (out/'src/fpga/build/ap_core.qsf').open('a',encoding='utf8') as f:
        f.write('\nset_global_assignment -name SYSTEMVERILOG_FILE ../core/menu_fade.sv\n')
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('sources','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();print(build(a.sources,a.out))
