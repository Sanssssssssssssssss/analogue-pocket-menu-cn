#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run existing checks plus timing and preserved-register reload control models."""
import argparse
import json
from pathlib import Path
import subprocess
from probe_isolation import check,sha,HERE

def handoff(prepared,bass,model,library,out):
    check(prepared,bass,model,library,out)
    out=Path(out).resolve();prepared=Path(prepared).resolve()
    receipt=json.loads((out/'receipt.json').read_text())
    for number in [11,12]:
        folder=prepared/'handoff'/f'Route{number}'
        p=subprocess.run([str(Path(bass).resolve()),'loader.asm'],cwd=folder,capture_output=True,text=True,timeout=60)
        (out/f'Route{number}-assembly.log').write_text(p.stdout+p.stderr);p.check_returncode()
        receipt['loaders'].append({'mode':f'Route{number}','assembly':'passed','bytecode_sha256':sha(folder/'loader.bin')})
        scenarios=['success','no-input','clock-stuck'] if number==11 else ['success','reentry-a','reentry-b','reentry-none','wrong-id']
        for scenario in scenarios:
            p=subprocess.run([str(Path(model).resolve()),str(folder/'loader.bin'),scenario],capture_output=True,text=True,timeout=60)
            p.check_returncode();data=json.loads(p.stdout)
            assert data['exit']==0 and data['hosts']==[0x4002] and data['loads']==[0],data
            assert all(0x60000000<=x<=0x600000FF for x in data['pmp_addresses']),data
            if number==11:
                tag={'success':0xD1000000,'no-input':0xD2000000,'clock-stuck':0xD3000000}[scenario]
                assert data['m']&0xFFFF0000==tag,data
                if scenario=='success':assert data['m']&0xFFFF==0x20,data
                elif scenario=='no-input':assert data['d']>=15000,data
                else:assert data['d']==0,data
            else:
                expected={'success':(0xC1,0x504C4100,[0]),'reentry-a':(0xC2,0x504C4100,[0]),
                          'reentry-b':(0xC2,0x504C4201,[1]),'reentry-none':(0xE6,0x504C4100,[]),'wrong-id':(0xE7,0,[0])}[scenario]
                assert (data['m'],data['d'],data['cores'])==expected,data
            receipt['cases'].append({'loader':f'Route{number}','scenario':scenario,**data})
    for name in ['timing_body.asm','reentry_body.asm','prepare_handoff.py','probe_handoff.py']:
        receipt['inputs'][name]=sha(HERE/name)
    receipt['scope']='Real bytecode with modeled FPGA, time and preserved VM registers; physical input and OS-triggered re-entry are not simulated'
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    return {'cases':len(receipt['cases']),'hardware_reentry':'not_tested','receipt':str(out/'receipt.json')}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['prepared','bass','model','library','out']:p.add_argument('--'+name,required=True)
    a=p.parse_args();print(json.dumps(handoff(a.prepared,a.bass,a.model,a.library,a.out)))
