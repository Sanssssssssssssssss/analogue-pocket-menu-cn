#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Probe menu fade alone or with the prepared video adapter; no card access."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',required=True)
p.add_argument('--build',help='Prepared GBA fade tree for an actual video game-bypass probe')
a=p.parse_args()
out=Path(a.out).resolve();here=Path(__file__).resolve().parent
if out.exists() or not out.is_relative_to(here.parents[1]/'.work'):p.error('Use a fresh directory under this repository .work')
out.mkdir(parents=True)
inputs=[here/'menu_fade.sv',here/'tb_fade.sv']
r=subprocess.run(['iverilog','-g2012','-s','tb_fade','-o',str(out/'fade.sim'),*map(str,inputs)],capture_output=True,text=True,timeout=30)
(out/'build.log').write_text(r.stdout+r.stderr,encoding='utf8');r.check_returncode()
r=subprocess.run(['vvp',str(out/'fade.sim')],capture_output=True,text=True,timeout=30)
(out/'simulation.log').write_text(r.stdout+r.stderr,encoding='utf8');r.check_returncode()
assert 'PASS:' in r.stdout
logs=[r.stdout.strip()]
if a.build:
    build=Path(a.build).resolve();video=build/'src/fpga/core/video_adapter.sv'
    bench=here/'tb_fade_video.sv';error=build/'src/fpga/build/gba_menu_error.hex'
    (out/'video.sv').write_text(video.read_text(encoding='utf8').replace('localparam int unsigned','localparam integer'),encoding='utf8')
    shutil.copy2(error,out/error.name)
    result=subprocess.run(['iverilog','-g2012','-s','tb_fade_video','-o',str(out/'video.sim'),str(here/'menu_fade.sv'),str(out/'video.sv'),str(bench)],capture_output=True,text=True,timeout=30)
    (out/'video-build.log').write_text(result.stdout+result.stderr,encoding='utf8');result.check_returncode()
    result=subprocess.run(['vvp',str(out/'video.sim')],cwd=out,capture_output=True,text=True,timeout=180)
    (out/'video.log').write_text(result.stdout+result.stderr,encoding='utf8');result.check_returncode()
    assert 'PASS:' in result.stdout
    logs.append(result.stdout.strip());inputs.extend([video,bench,error])
receipt={'result':'passed','scope':'Standalone RTL gain/handshake assumptions only; not connected to video_adapter or any game core',
         'framebuffer_storage_bits':0,'fade_in_frames':8,'fade_out_frames':4,'pixel_patterns_per_gain':256,
         'checks':['frame-tick-only gain updates','all nine gains','blank upload wait','bit-identical game bypass','reset during fade'],
         'not_validated':['actual clock crossing and framebuffer integration','complete GBA timing','fitter resources','hardware appearance'],
         'inputs':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs}}
if a.build:
    receipt['scope']='Standalone gain plus actual GBA video adapter with a synthetic game framebuffer; no game CPU or physical device'
    receipt['game_raster_pixels_compared']=38400
    receipt['checks'].append('actual game raster bypass and black menu re-entry')
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
print('\n'.join(logs))
