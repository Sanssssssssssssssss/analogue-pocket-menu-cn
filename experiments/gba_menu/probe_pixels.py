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

p=argparse.ArgumentParser(description=__doc__)
for name in ('build','page','intel-model','out'):p.add_argument('--'+name,required=True)
a=p.parse_args();out=Path(a.out).resolve();build=Path(a.build).resolve()
out.mkdir(parents=True,exist_ok=False)
page=Path(a.page).read_bytes();base=struct.unpack_from('<I',page,12)[0]
pixels=struct.unpack('<38400H',page[base:base+76800])
(out/'pixels.hex').write_text(''.join(f'{v:04x}\n' for v in pixels))
shutil.copy2(build/'src/fpga/build/gba_menu_error.hex',out)
here=Path(__file__).resolve().parent
inputs=[here/'tb_pixels.sv',here/'gba_menu_pixels.sv',build/'src/fpga/core/video_adapter.sv',
        build/'src/fpga/pocket/data_loader.sv',Path(a.intel_model).resolve()]
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
         'result':'passed','pixels':38400,'input_hashes':{str(x.relative_to(build)) if x.is_relative_to(build) else x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs}}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
