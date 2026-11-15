#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify the exact GBA text loader with the licensed Intel simulation models."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True);p.add_argument('--out',required=True);p.add_argument('--intel-model',required=True);a=p.parse_args()
out=Path(a.out).resolve();build=Path(a.build).resolve()
if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
out.mkdir(parents=True)
inputs=[Path(__file__).with_name('tb_text_ingress.sv'),build/'src/fpga/pocket/data_loader.sv',Path(a.intel_model).resolve()]
r=subprocess.run(['iverilog','-g2012','-s','tb_text_ingress','-o',str(out/'text.sim'),*map(str,inputs)],capture_output=True,text=True,timeout=60)
(out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
r=subprocess.run(['vvp',str(out/'text.sim')],capture_output=True,text=True,timeout=60)
(out/'simulation.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
if 'PASS:' not in r.stdout:raise ValueError('No text ingress pass marker')
(out/'receipt.json').write_text(json.dumps({'result':'passed','scope':'Synthetic bitmap columns through actual upstream data_loader and Intel FIFO; no card/game CPU/hardware',
    'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}},indent=2)+'\n')
