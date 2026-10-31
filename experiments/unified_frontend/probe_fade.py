#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Probe the isolated transition candidate; no core integration or card access."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',required=True);a=p.parse_args()
out=Path(a.out).resolve();here=Path(__file__).resolve().parent
if out.exists():p.error('Use a fresh output directory')
out.mkdir(parents=True)
inputs=[here/'menu_fade.sv',here/'tb_fade.sv']
r=subprocess.run(['iverilog','-g2012','-s','tb_fade','-o',str(out/'fade.sim'),*map(str,inputs)],capture_output=True,text=True,timeout=30)
(out/'build.log').write_text(r.stdout+r.stderr,encoding='utf8');r.check_returncode()
r=subprocess.run(['vvp',str(out/'fade.sim')],capture_output=True,text=True,timeout=30)
(out/'simulation.log').write_text(r.stdout+r.stderr,encoding='utf8');r.check_returncode()
assert 'PASS:' in r.stdout
receipt={'result':'passed','scope':'Standalone RTL gain/handshake assumptions only; not connected to video_adapter or any game core',
         'framebuffer_storage_bits':0,'fade_in_frames':8,'fade_out_frames':4,'pixel_patterns_per_gain':256,
         'checks':['frame-tick-only gain updates','all nine gains','blank upload wait','bit-identical game bypass','reset during fade'],
         'not_validated':['actual clock crossing and framebuffer integration','complete GBA timing','fitter resources','hardware appearance'],
         'inputs':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs}}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
print(r.stdout.strip())
