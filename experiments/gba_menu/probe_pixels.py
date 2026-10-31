#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Simulate actual upstream FIFO/data_loader/video RTL, capturing a complete menu."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from prepare_build import replace

p=argparse.ArgumentParser(description=__doc__)
for name in ('build','page','intel-model','out'):p.add_argument('--'+name,required=True)
p.add_argument('--fade',action='store_true',help='Compare all eight raster gains in the separate fade candidate')
a=p.parse_args();out=Path(a.out).resolve();build=Path(a.build).resolve()
out.mkdir(parents=True,exist_ok=False)
page=Path(a.page).read_bytes();base=struct.unpack_from('<I',page,12)[0]
pixels=struct.unpack('<38400H',page[base:base+76800])
(out/'pixels.hex').write_text(''.join(f'{v:04x}\n' for v in pixels))
shutil.copy2(build/'src/fpga/build/gba_menu_error.hex',out)
here=Path(__file__).resolve().parent
bench=here/'tb_pixels.sv'
if a.fade:
    bench=out/'tb_pixels.sv'
    text=replace((here/'tb_pixels.sv').read_text(),".menu_fault(1'b0),",".menu_fault(1'b0),.menu_active(owned),")
    text=replace(text,'integer i,file,count;', '''integer i,file,count,gain_frame;
    function [23:0] gain_color(input [23:0] p,input integer gain);
        integer r,g,b;
        begin r=(p[23:16]*gain)>>3;g=(p[15:8]*gain)>>3;b=(p[7:0]*gain)>>3;
            gain_color={r[7:0],g[7:0],b[7:0]};end
    endfunction''')
    text=replace(text,'show=1;wait(visible);@(posedge vs);@(negedge vs);',
                 'show=1;wait(visible);for(gain_frame=1;gain_frame<=8;gain_frame=gain_frame+1)begin')
    text=replace(text,'$fopen("menu.ppm","wb")','$fopen($sformatf("menu-%0d.ppm",gain_frame),"wb")')
    text=replace(text,'if(rgb!==color(pixels[count]))','if(rgb!==gain_color(color(pixels[count]),gain_frame))')
    text=replace(text,'count,rgb,color(pixels[count])','count,rgb,gain_color(color(pixels[count]),gain_frame)')
    text=replace(text,'$fclose(file);show=0;', '''$fclose(file);
        $display("PASS: fade raster gain %0d, 38400 pixels",gain_frame);
        if(gain_frame<8)begin @(posedge vs);@(negedge vs);end
        end
        show=0;''')
    text=replace(text,'#150000000;','#500000000;')
    bench.write_text(text)
inputs=[bench,here/'gba_menu_pixels.sv',build/'src/fpga/core/video_adapter.sv',
        build/'src/fpga/pocket/data_loader.sv',Path(a.intel_model).resolve()]
if a.fade:inputs.append(build/'src/fpga/core/menu_fade.sv')
# Icarus does not accept "localparam int unsigned"; removing signedness in this
# simulation copy leaves all positive raster constants unchanged. Synthesis uses original.
video=out/'video_adapter.sv';video.write_text(inputs[2].read_text().replace('localparam int unsigned','localparam integer'))
rtl=[video if x==inputs[2] else x for x in inputs]
cmd=['iverilog','-g2012','-s','tb_pixels','-o',str(out/'pixels.sim'),*map(str,rtl)]
r=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
(out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
r=subprocess.run(['vvp',str(out/'pixels.sim')],cwd=out,capture_output=True,text=True,timeout=900)
(out/'simulation.log').write_text(r.stdout+r.stderr)
print(r.stdout+r.stderr);r.check_returncode()
receipt={'scope':'Actual Intel FIFO, upstream data_loader and patched video_adapter; no GBA CPU or physical device',
         'fade_candidate':a.fade,'result':'passed','pixels':38400,'raster_frames_compared':8 if a.fade else 1,'input_hashes':{str(x.relative_to(build)) if x.is_relative_to(build) else x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs}}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
