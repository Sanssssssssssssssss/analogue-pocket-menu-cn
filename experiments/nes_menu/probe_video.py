#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import argparse,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();out=Path(a.out).resolve()
assert not out.exists() and out.is_relative_to(ROOT/'.work');out.mkdir(parents=True)
# Error ROM is inactive in this test; the tested signal chain still instantiates it.
(out/'gba_menu_error.hex').write_text('0000000000000000\n'*240)
inputs=[HERE/'menu_video.sv',HERE/'tb_video.sv']
r=subprocess.run(['iverilog','-g2012','-s','tb_video','-o',str(out/'video.sim'),*map(str,inputs)],capture_output=True,text=True)
(out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
r=subprocess.run(['vvp',str(out/'video.sim')],cwd=out,capture_output=True,text=True,timeout=90)
(out/'simulation.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
assert 'PASS:' in r.stdout
(out/'receipt.json').write_text(json.dumps({'result':'passed','menu_pixels':38400,'raster_pixels':61440,
    'game_bypass_patterns':256,'scope':'Actual standalone menu raster and inferred memory; no game core or physical device',
    'inputs':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs}},indent=2)+'\n')
