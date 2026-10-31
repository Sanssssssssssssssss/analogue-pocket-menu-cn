#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage four separate diagnostic entries after reviewing complete board reports; no card access."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from apf_metadata import check_core

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write_json(p,value):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')

def audit(build,name):
    fpga=build/name/'src/fpga';folder=fpga/'output_files'
    flow=(folder/'ap_core.flow.rpt').read_text();fit=(folder/'ap_core.fit.summary').read_text()
    sta=(folder/'ap_core.sta.summary').read_text();report=(folder/'ap_core.sta.rpt').read_text()
    if not re.search(r'Flow Status\s*; Successful',flow) or 'Fitter Status : Successful' not in fit:
        raise ValueError('Incomplete board compilation: '+name)
    slack=[float(x) for x in re.findall(r'Slack\s*:\s*(-?[\d.]+)',sta)]
    tns=[float(x) for x in re.findall(r'TNS\s*:\s*(-?[\d.]+)',sta)]
    if not slack or min(slack)<0 or len(slack)!=len(tns) or any(tns):raise ValueError('Timing failure: '+name)
    for kind in ['Clocks','Input Ports','Output Ports']:
        if int(re.search(r'; Unconstrained '+kind+r'\s*; (\d+)',report)[1]):raise ValueError('Unreviewed timing coverage: '+kind)
    if 'Total virtual pins : 0' not in fit:raise ValueError('Virtual pins present')
    source=fpga/'core/core_top.v';text=source.read_text()
    if "assign audio_mclk = 0;" not in text:raise ValueError('Trial silence modification missing')
    for field in ['read','write','getfile','openfile']:
        if f'wire            target_dataslot_{field} = 0;' not in text:raise ValueError('Target file operation enabled')
    return {'program':name,'compile':'successful','timing_records':len(slack),'minimum_reported_slack_ns':min(slack),'all_tns_zero':True,
        'board_io_scope':'APF protocol I/O explicitly excepted, following existing GBA constraints; no external setup/hold signoff',
        'rbf_sha256':sha(folder/'ap_core.rbf'),'source_sha256':{p.relative_to(fpga).as_posix():sha(p) for p in [source,fpga/'core/route_probe.sv',fpga/'core/core_constraints.sdc']},
        'reports_sha256':{p.name:sha(p) for p in [folder/'ap_core.flow.rpt',folder/'ap_core.fit.summary',folder/'ap_core.sta.summary']}}

def stage(build,validation,out,isolation=False,interaction=False):
    if isolation and interaction:raise ValueError('Select one diagnostic profile')
    build=Path(build).resolve();out=Path(out).resolve()
    if out.exists() or not all(p.is_relative_to(ROOT/'.work') for p in [out,build]):raise ValueError('Use fresh checkout .work output and local build')
    proof=json.loads(Path(validation).read_text());here=Path(__file__).resolve().parent
    inputs=['loader.asm','route_probe.sv','tb_probe.sv']
    if isolation or interaction:inputs+=['isolation_loader.asm','prepare_isolation.py','vm_contract.rs','probe_isolation.py','prepare_probe.py','prepare_trial.py']
    for name in inputs:
        if proof['inputs'][name]!=sha(here/name):raise ValueError('Offline validation is stale: '+name)
    reviewed=[audit(build,n) for n in ['A','B']]
    for item in reviewed:
        if item['source_sha256']['core/route_probe.sv']!=sha(here/'route_probe.sv'):raise ValueError('Compiled probe source differs')
    reverse=bytes(int(f'{n:08b}'[::-1],2) for n in range(256));assert reverse.translate(reverse)==bytes(range(256))
    out.mkdir(parents=True);files=out/'files'
    if isolation:
        entries=[(4,'Route4','Boot A without polling'),(5,'Route5','Read and report identity A'),
                 (6,'Route6','Load A then B without input'),(7,'Route7','Cold boot B')]
    elif interaction:
        entries=[(8,'pre-init','Corrected input before init'),(9,'reset-exit','Corrected input after reset exit'),
                 (10,'full-init','Corrected input after full init')]
    else:
        entries=list(zip(range(4),[None,'pre-init','reset-exit','full-init'],
            ['Control: no loader','Input before init','Input after reset exit','Input after full init']))
    for i,mode,description in entries:
        folder=files/f'Cores/pocketlab.Route{i}';folder.mkdir(parents=True)
        for name in ['audio','input','variants','video']:shutil.copy2(build/'A'/f'{name}.json',folder/f'{name}.json')
        core=json.loads((build/'A/core.json').read_text())['core']
        core['metadata'].update(platform_ids=['routetest'],shortname=f'Route{i}',author='pocketlab',description=description,
            url='https://github.com/Sanssssssssssssssss/analogue-pocket-menu-cn',version='0.0.3-input' if interaction else '0.0.2-isolate' if isolation else '0.0.1-trial',date_release='2026-11-01')
        core['framework']['hardware']={'link_port':False,'cartridge_adapter':'0x80000000'}
        core['cores']=[{'name':n,'id':j,'filename':f'probe_{n.lower()}.rbf_r'} for j,n in enumerate(['A','B'])]
        for name in ['A','B']:
            raw=(build/name/'src/fpga/output_files/ap_core.rbf').read_bytes()
            translated=raw.translate(reverse);assert translated.translate(reverse)==raw
            (folder/f'probe_{name.lower()}.rbf_r').write_bytes(translated)
        if mode:
            loader=build/('isolation' if isolation else 'loaders')/mode/'loader.bin'
            expected=next(x['bytecode_sha256'] for x in proof['loaders'] if x['mode']==mode)
            if sha(loader)!=expected or loader.stat().st_size>8192:raise ValueError('Loader differs from assembled validation')
            shutil.copy2(loader,folder/'loader.bin');core['framework']['chip32_vm']='loader.bin'
        write_json(folder/'core.json',{'core':core});check_core(folder)
        write_json(folder/'input.json',{'input':{'magic':'APF_VER_1','controllers':[{'type':'default','mappings':[{'id':0,'name':'A','key':'pad_btn_a'},{'id':1,'name':'B','key':'pad_btn_b'}]}]}})
        write_json(folder/'data.json',{'data':{'magic':'APF_VER_1','data_slots':[{'id':0,'name':'Probe seed','required':True,'filename':'probe.dat','size_exact':16,'address':'0x60000080','nonvolatile':False}]}})
        fields=[('ID',0),('R',4),('U',8),('K',0x1C),('P',0x90),('M',0xA0),('D',0xA4)]
        write_json(folder/'interact.json',{'interact':{'magic':'APF_VER_1','variables':[{'name':n,'id':60000+j,'type':'number_u32','enabled':False,'address':hex(0x60000000+offset)} for j,(n,offset) in enumerate(fields)],'messages':[]}})
    seed=files/'Assets/routetest/common/probe.dat';seed.parent.mkdir(parents=True);seed.write_bytes(b'PLAB-PROBE-V1'.ljust(16,b'\0'))
    write_json(files/'Platforms/routetest.json',{'platform':{'category':'Handheld','name':'Pocket Lab Test','manufacturer':'Pocket Lab','year':2026}})
    images=files/'Platforms/_images';images.mkdir();shutil.copy2(build/'A/dist/platforms/_images/ex_platform.bin',images/'routetest.bin')
    manifest={'date':'2026-11-01','scope':'Isolated no-game diagnostic trial; not a unified frontend','device_acceptance':'pending','save_slots':0,'firmware_files':0,'board_builds':reviewed,
        'files':[{'path':p.relative_to(files).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files.rglob('*')) if p.is_file()]}
    write_json(out/'trial-manifest.json',manifest)
    return {'out':str(out),'files':len(manifest['files']),'bytes':sum(p['bytes'] for p in manifest['files'])}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['build','validation','out']:p.add_argument('--'+n,required=True)
    profiles=p.add_mutually_exclusive_group()
    profiles.add_argument('--isolation',action='store_true',help='Stage only new Route4-7 minimal loaders')
    profiles.add_argument('--interaction',action='store_true',help='Stage only new Route8-10 corrected input loaders')
    a=p.parse_args();print(json.dumps(stage(a.build,a.validation,a.out,a.isolation,a.interaction)))
