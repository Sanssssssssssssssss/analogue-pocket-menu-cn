#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description='Check the actual asynchronous texture read bridge');p.add_argument('--out',required=True);a=p.parse_args();out=Path(a.out).resolve()
if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
out.mkdir(parents=True);inputs=[HERE/'memory_bridge.sv',HERE/'tb_memory_bridge.sv']
r=subprocess.run(['iverilog','-g2012','-s','tb_memory_bridge','-o',str(out/'bridge.sim'),*map(str,inputs)],capture_output=True,text=True,timeout=60)
(out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
r=subprocess.run(['vvp',str(out/'bridge.sim')],capture_output=True,text=True,timeout=60)
(out/'simulation.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
if 'PASS:' not in r.stdout:raise ValueError('Missing bridge pass marker')
(out/'receipt.json').write_text(json.dumps({'result':'passed','scope':'Actual bridge with independent clocks and synthetic memory; no hardware/SDRAM device',
    'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}},indent=2)+'\n')
