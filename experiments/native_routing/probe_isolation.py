#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check diagnostic RTL and real bytecode with explicitly modeled FPGA/host replies."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def check(prepared,bass,model,library,out):
    prepared=Path(prepared).resolve();out=Path(out).resolve()
    if out.exists() or not all(p.is_relative_to(HERE.parents[1]/'.work') for p in [out,prepared]):
        raise ValueError('Use fresh checkout .work output and local prepared sources')
    out.mkdir(parents=True)
    def run(args,cwd=out):
        r=subprocess.run(list(map(str,args)),cwd=cwd,capture_output=True,text=True,timeout=60)
        if r.returncode:raise RuntimeError(r.stdout+r.stderr)
        return r.stdout+r.stderr
    sources=['route_probe.sv','tb_probe.sv','loader.asm','isolation_loader.asm','prepare_probe.py',
             'prepare_trial.py','prepare_isolation.py','vm_contract.rs','probe_isolation.py']
    log=run(['iverilog','-g2012','-s','tb_probe','-o',out/'probe.sim',HERE/'route_probe.sv',HERE/'tb_probe.sv'])
    log+=run(['vvp',out/'probe.sim']);assert 'PASS:' in log
    (out/'rtl.log').write_text(log,encoding='utf8')
    cases=[];loaders=[]
    def assemble(folder,name):
        log=run([Path(bass).resolve(),'loader.asm'],cwd=folder)
        (out/(name+'-assembly.log')).write_text(log,encoding='utf8')
        binary=folder/'loader.bin';assert 0<binary.stat().st_size<=8192
        return binary
    def execute(binary,scenario):
        data=json.loads(run([Path(model).resolve(),binary,scenario]))
        assert data['model'] is True and data['exit']!=2,data
        return data
    for mode in ['pre-init','reset-exit','full-init']:
        binary=assemble(prepared/'loaders'/mode,mode)
        loaders.append({'mode':mode,'assembly':'passed','bytecode_sha256':sha(binary)})
        for scenario,exit_code,result,detail,cores in [
            ('success',0,0xA0,0x504C4100,[0,1,0]),
            ('skip-switch',0,0xE3,0x504C4100,[0,1]),
            ('skip-return',0,0xE4,0x504C4201,[0,1,0]),
            ('no-input',0,0xE2,0,[0]),
            ('clock-stuck',0,0xE2,0,[0]),
            ('wrong-id',1,0,0,[0])]:
            data=execute(binary,scenario)
            assert (data['exit'],data['m'],data['d'],data['cores'])==(exit_code,result,detail,cores),(mode,scenario,data)
            assert all(0x60000000<=x<=0x600000FF for x in data['pmp_addresses']),data
            assert data['loads']==[0]*len(cores),data
            cases.append({'loader':mode,'scenario':scenario,**data})
    # Reproduce the actual BASS address-truncation failure to guard this regression.
    broken=out/'truncated-expression';broken.mkdir()
    source=(prepared/'loaders/pre-init/loader.asm').read_text(encoding='utf8')
    for offset in [0x08,0x0C,0x10,0x14,0x20,0x24]:
        source=source.replace(f'#0x{0x60000000+offset:08X}',f'#base+0x{offset:02X}')
    (broken/'loader.asm').write_text(source,encoding='utf8')
    data=execute(assemble(broken,'truncated-expression'),'success')
    assert data['m']==0 and data['d']==0 and data['cores']==[0] and 0x20 in data['pmp_addresses'],data
    cases.append({'loader':'negative-compiler-regression','scenario':'truncated-expression',**data})
    expected={4:(0,0,[0],[0]),5:(0xB1,0x504C4100,[0],[0]),
              6:(0xB2,0x504C4201,[0,1],[0,0]),7:(0,0,[1],[0])}
    for number,(result,detail,cores,loads) in expected.items():
        name=f'Route{number}';binary=assemble(prepared/'isolation'/name,name)
        data=execute(binary,'success')
        assert (data['exit'],data['m'],data['d'],data['cores'],data['hosts'],data['loads'])==(0,result,detail,cores,[0x4002],loads),(name,data)
        cases.append({'loader':name,'scenario':'modeled-normal-host',**data})
        loaders.append({'mode':name,'assembly':'passed','bytecode_sha256':sha(binary)})
    receipt={'date':'2026-11-01','scope':'Real instruction execution with synthetic FPGA/host replies; not Pocket behavior',
        'rtl':'passed including read-only diagnostic aliases','cases':cases,'loaders':loaders,
        'inputs':{name:sha(HERE/name) for name in sources},
        'tools':{Path(x).name:sha(x) for x in [bass,model,library]},
        'hardware_reconfiguration':'not_tested','card_access':False}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    return {'cases':len(cases),'rtl':'passed','receipt':str(out/'receipt.json'),'hardware_reconfiguration':'not_tested'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['prepared','bass','model','library','out']:p.add_argument('--'+name,required=True)
    a=p.parse_args();print(json.dumps(check(a.prepared,a.bass,a.model,a.library,a.out)))
