#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare extracted geometry against the actual accepted GB/GBC renderer."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
from prepare_geometry import prepare,ROOT
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--intel-model',required=True);p.add_argument('--compact',action='store_true');a=p.parse_args();out=prepare(a.out,a.compact)
for name in ['font_cn.hex','font5x7.hex','font_cn_width.hex','font5x7_width.hex']:
    shutil.copy2(ROOT/'core/src'/name,out/name)
inputs=[ROOT/'core/src/core/cover_picker.sv',out/'coverflow_geometry.sv',HERE/'tb_geometry.sv',ROOT/'core/src/core/picker_dpram.v',Path(a.intel_model).resolve()]
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
r=subprocess.run(['iverilog','-g2012','-s','tb_geometry','-o',str(out/'geometry.sim'),*map(str,inputs)],capture_output=True,text=True,timeout=60)
(out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
r=subprocess.run(['vvp',str(out/'geometry.sim')],cwd=out,capture_output=True,text=True,timeout=60)
(out/'simulation.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr,flush=True);r.check_returncode()
if 'PASS:' not in r.stdout:raise ValueError('Missing geometry pass marker')
(out/'receipt.json').write_text(json.dumps({'result':'passed','scope':'Extracted geometry vs actual frozen GB/GBC CoverFlow; original control disabled, no game CPU/card/device',
    'cases':['counts 1,2,3,5,127,128,129,2047','96 left/right/wrap animations','all four cover positions, scales, brightness, image indices and validity','title fade','disabled-state reset'],
    'compact':a.compact,'inputs':hashes},indent=2)+'\n')
