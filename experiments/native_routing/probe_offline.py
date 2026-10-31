#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check probe RTL and assemble loaders; the logging VM must refuse missing FPGA IDs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p=argparse.ArgumentParser(description=__doc__)
for name in ['prepared','bass','simulator','out']:p.add_argument('--'+name,required=True)
a=p.parse_args();here=Path(__file__).resolve().parent;prepared=Path(a.prepared).resolve();out=Path(a.out).resolve()
if out.exists() or not out.is_relative_to(here.parents[1]/'.work'):p.error('Use a fresh output in this checkout/.work')
out.mkdir(parents=True)
def run(cmd,cwd=out):
    r=subprocess.run(list(map(str,cmd)),cwd=cwd,capture_output=True,text=True,timeout=60)
    return r
rtl=[here/'route_probe.sv',here/'tb_probe.sv']
r=run(['iverilog','-g2012','-s','tb_probe','-o',out/'probe.sim',*rtl]);(out/'rtl-build.log').write_text(r.stdout+r.stderr);r.check_returncode()
r=run(['vvp',out/'probe.sim']);(out/'rtl.log').write_text(r.stdout+r.stderr);r.check_returncode();assert 'PASS:' in r.stdout
loaders=[]
for name in ['pre-init','reset-exit','full-init']:
    folder=prepared/'loaders'/name
    r=run([Path(a.bass).resolve(),'loader.asm'],cwd=folder)
    (out/(name+'-assembly.log')).write_text(r.stdout+r.stderr);r.check_returncode()
    r=run([Path(a.simulator).resolve(),'--bin',folder/'loader.bin','--json'])
    data=json.loads(r.stdout)
    # This VM's PMPR/CORE/HOST are stubs. A success here would be a false positive.
    assert r.returncode==1 and any('NO_FPGA:' in line for line in data['logs']), (name,r.stdout,r.stderr)
    assert data['core']==0
    assert not any('IDENTITY_A_B_A:' in line for line in data['logs'])
    (out/(name+'-stub-trace.json')).write_text(json.dumps(data,indent=2)+'\n')
    loaders.append({'mode':name,'assembly':'passed','logging_vm':'refused missing FPGA identity as required',
                    'bytecode_sha256':hashlib.sha256((folder/'loader.bin').read_bytes()).hexdigest()})
receipt={'date':'2026-11-01','scope':'Standalone probe RTL plus real loader assembly and negative stub-VM checks; no host reconfiguration or video/input acceptance',
    'rtl':'passed','loaders':loaders,'card_access':False,'hardware_reconfiguration':'not_tested',
    'inputs':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in [*rtl,here/'loader.asm',here/'prepare_probe.py',Path(__file__)]},
    'tools':{Path(x).name:hashlib.sha256(Path(x).read_bytes()).hexdigest() for x in [a.bass,a.simulator]}}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
