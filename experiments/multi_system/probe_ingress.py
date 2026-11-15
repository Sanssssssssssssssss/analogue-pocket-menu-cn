#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute frozen GBA/NES ingress RTL using an installed Intel FIFO model."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p=argparse.ArgumentParser(description=__doc__)
for flag in ('sources','intel-model','out'):p.add_argument('--'+flag,required=True)
a=p.parse_args();out=Path(a.out).resolve()
if out.exists():raise ValueError('Use a fresh output directory')
out.mkdir(parents=True)
here=Path(__file__).resolve().parent;sources=Path(a.sources).resolve()
inputs=[here/'tb_ingress.sv',sources/'gba/src/fpga/pocket/apf_write_ingress.sv',
        sources/'nes/target/pocket/data_loader.sv',Path(a.intel_model).resolve()]
cmd=['iverilog','-g2012','-s','tb_ingress','-o',str(out/'ingress.sim'),*map(str,inputs)]
build=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
(out/'build.log').write_text(build.stdout+build.stderr)
build.check_returncode()
normal=subprocess.run(['vvp',str(out/'ingress.sim')],capture_output=True,text=True,timeout=30)
(out/'cold-load.log').write_text(normal.stdout+normal.stderr)
assert normal.returncode==0 and 'PASS: real GBA/NES ingress' in normal.stdout
reload=subprocess.run(['vvp',str(out/'ingress.sim'),'+reload'],capture_output=True,text=True,timeout=30)
(out/'reload-observation.log').write_text(reload.stdout+reload.stderr)
assert reload.returncode!=0 and 'APF startup write arrived after completion fence' in reload.stdout
receipt={'scope':'Actual frozen GBA/NES ingress RTL with Intel FIFO simulation model; no CPU, game or physical memory',
         'cold_load':'passed endian/address/backpressure/completion checks',
         'reload':'upstream GBA simulation guard rejects second transaction after startup fence',
         'reload_limit':'guard is simulation-only; this does not prove a hardware failure',
         'physical_card_access':False,
         'input_hashes':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs}}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
