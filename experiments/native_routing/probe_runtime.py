#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check runtime command RTL and loader branches; do not model a VM callback from files."""
import argparse
import json
from pathlib import Path
import subprocess
from probe_isolation import HERE,sha

INPUTS=['runtime_request.sv','tb_runtime.sv','prepare_runtime.py','probe_runtime.py',
        'reentry_body.asm','isolation_loader.asm','vm_contract.rs','prepare_probe.py','prepare_trial.py']
HARDWARE=['core/core_top.v','core/runtime_request.sv','core/route_probe.sv',
          'core/core_bridge_cmd.v','apf/common.v','core/core_constraints.sdc','ap_core.qsf']


def check(prepared,bass,model,library,out):
    prepared=Path(prepared).resolve();out=Path(out).resolve()
    if out.exists() or not all(p.is_relative_to(HERE.parents[1]/'.work') for p in [out,prepared]):
        raise ValueError('Use fresh checkout .work output and prepared sources')
    out.mkdir(parents=True)
    def run(args,cwd=out):
        p=subprocess.run(list(map(str,args)),cwd=cwd,capture_output=True,text=True,timeout=60)
        if p.returncode:raise RuntimeError(p.stdout+p.stderr)
        return p.stdout+p.stderr
    fpga=prepared/'A/src/fpga'
    assert sha(fpga/'core/runtime_request.sv')==sha(HERE/'runtime_request.sv')
    rtl=run(['iverilog','-g2012','-s','tb_runtime','-o',out/'runtime.sim',
             HERE/'runtime_request.sv',HERE/'tb_runtime.sv',fpga/'core/core_bridge_cmd.v',fpga/'apf/common.v'])
    rtl+=run(['vvp',out/'runtime.sim']);assert 'PASS:' in rtl
    (out/'rtl.log').write_text(rtl)
    cases=[];loaders=[]
    for number,mode in [(13,1),(14,2)]:
        folder=prepared/'runtime'/f'Route{number}';binary=folder/'loader.bin'
        log=run([Path(bass).resolve(),'loader.asm'],cwd=folder)
        (out/f'Route{number}-assembly.log').write_text(log)
        assert 0<binary.stat().st_size<=8192
        loaders.append({'mode':f'Route{number}','assembly':'passed','bytecode_sha256':sha(binary)})
        for scenario,expected in [('success',(0xC1,0x504C4100,[0])),('reentry-a',(0xC2,0x504C4100,[0])),
            ('reentry-b',(0xC2,0x504C4201,[1])),('reentry-none',(0xE6,0x504C4100,[])),('wrong-id',(0xE7,0,[0]))]:
            data=json.loads(run([Path(model).resolve(),binary,scenario]))
            assert data['model'] and data['exit']==0 and data['hosts']==[0x4002] and data['loads']==[0],data
            assert (data['m'],data['d'],data['cores'])==expected and data['arms']==[mode],data
            assert set(data['pmp_addresses'])<=set([0x60000000,0x60000010,0x60000020,0x60000024,0x60000030,0x60000034]),data
            cases.append({'loader':f'Route{number}','scenario':scenario,**data})
    receipt={'scope':'Runtime helper + actual SDK command RTL with synthetic host responses; real bytecode with modeled FPGA and preserved VM registers. No automatic OS callback is simulated.',
        'rtl':'passed','cases':cases,'loaders':loaders,'card_access':False,'automatic_reentry':'not_tested',
        'inputs':{n:sha(HERE/n) for n in INPUTS},
        'hardware_sources':{n:{p:sha(prepared/n/'src/fpga'/p) for p in HARDWARE} for n in ['A','B']},
        'tools':{Path(p).name:sha(p) for p in [bass,model,library]}}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return {'rtl':'passed','modeled_loader_cases':len(cases),'automatic_reentry':'not_tested','receipt':str(out/'receipt.json')}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['prepared','bass','model','library','out']:p.add_argument('--'+name,required=True)
    a=p.parse_args();print(json.dumps(check(a.prepared,a.bass,a.model,a.library,a.out)))
