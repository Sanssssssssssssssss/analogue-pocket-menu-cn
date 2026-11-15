#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare a separate GBA cover-slide candidate; accepted sources stay unchanged."""
import argparse,shutil
from pathlib import Path
from prepare_build import prepare,replace
HERE=Path(__file__).resolve().parent

def integrate_motion(out):
    core=out/'src/fpga/core/core_top.sv';s=core.read_text(encoding='utf8')
    s=replace(s,'video_adapter video_out (', '''reg [31:0] motion_keys=0;
reg motion_forward=1;
always @(posedge clk_74a)begin
    motion_keys<=cont1_key;
    if((cont1_key[0] && !motion_keys[0]) || (cont1_key[2] && !motion_keys[2]))motion_forward<=0;
    else if((cont1_key[1] && !motion_keys[1]) || (cont1_key[3] && !motion_keys[3]))motion_forward<=1;
end
video_adapter video_out (
    .menu_active(ui_owned),.menu_motion(ui_owned && !ui_bound),.menu_forward(motion_forward),''')
    core.write_text(s,encoding='utf8',newline='\n')
    shutil.copy2(HERE/'gba_motion_video.sv',out/'src/fpga/core/video_adapter.sv')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sources',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    out=prepare(a.sources,a.out,True);integrate_motion(out);print(out)
