#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify the complete WS fit and package a separate offline candidate."""
import argparse
import csv
import hashlib
import importlib.util
import json
import re
import shutil
from pathlib import Path
_spec=importlib.util.spec_from_file_location('ws_prepare_for_package',Path(__file__).with_name('prepare.py'))
_prepare=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_prepare)
ROOT,WORK,load,write=_prepare.ROOT,_prepare.WORK,_prepare.load,_prepare.write


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package(candidate,build,out):
    candidate,build,out=map(lambda p:Path(p).resolve(),(candidate,build,out))
    if out.exists() or not out.is_relative_to(WORK):raise ValueError('Fresh WS output required')
    compiled=build/'compiled'
    outputs=compiled/'src/fpga/output_files'
    if (build/'exit.txt').read_text().strip()!='0':raise ValueError('Full compile did not succeed')
    timings=re.findall(r'Type\s*:\s*([^\n]+)\s*\nSlack\s*:\s*([-0-9.]+)\s*\nTNS\s*:\s*([-0-9.]+)',
        (outputs/'ap_core.sta.summary').read_text())
    if len(timings)!=76 or len({row[0].split(' Model ')[0] for row in timings})!=4:
        raise ValueError('Expected all four corners and all 76 native timing checks')
    if any(float(row[1])<0 or float(row[2])<0 for row in timings):
        raise ValueError('Timing violation; candidate must not be packaged')
    critical=[line for line in (build/'compile.log').read_text().splitlines() if 'Critical Warning' in line]
    # Quartus rounds the inherited 1280-word pause font to a 2048-word block.
    # Only label IDs 0..9 exist; its unused addresses are explicitly filled 0.
    if any(not ('Critical Warning (127005)' in line and 'Memory depth (2048)' in line
        and 'memory depth (1280)' in line and 'native_pause_pixels' in line) for line in critical):
        raise ValueError('Unresolved critical warning: '+str(critical))
    checker=load('ws_sram_report',ROOT/'experiments/gba_coverflow/probe_timing.py')
    sram=checker.summarize(build/'sram-io.tsv')
    proof=json.loads((build/'sram-proof.json').read_text())
    if proof['inputs']!={name:sha(compiled/name) for name in proof['inputs']} or proof['report_sha256']!=sha(build/'sram-io.tsv'):
        raise ValueError('SRAM proof does not bind this fitted bitstream/source')
    if proof['budget_ns']!=4.25 or proof['checker_sha256']!=sha(build/'check_sram_timing.tcl') or proof['model_sha256']!=sha(ROOT/'experiments/gba_coverflow/sim_sram.sv'):
        raise ValueError('SRAM proof model/checker differs')
    validation_path=WORK/('freeze-'+candidate.name+'.json')
    validation=None
    if validation_path.is_file():
        validation=json.loads(validation_path.read_text())
        if validation['preparation_sha256']!=sha(candidate/'preparation.json'):
            raise ValueError('Validation bound a different candidate')
        for name,digest in validation['evidence'].items():
            if sha(WORK/name)!=digest:raise ValueError('Validation evidence changed: '+name)
    receipt=json.loads((candidate/'preparation.json').read_text())
    checked={}
    for entry in receipt['files']:
        rel=entry['path'];before=(candidate/rel).read_bytes();after=(compiled/rel).read_bytes()
        if hashlib.sha256(before).hexdigest()!=entry['sha256']:raise ValueError('Candidate source changed: '+rel)
        if rel=='src/fpga/ap_core.qsf':
            ignored=('set_global_assignment -name LAST_QUARTUS_VERSION ','set_global_assignment -name SEED ')
            before,after=([line for line in raw.decode().splitlines() if not line.startswith(ignored)] for raw in (before,after))
            # Quartus removes the upstream AUTO FIT assignment superseded by
            # our later STANDARD FIT. Require the same effective final value.
            standard='set_global_assignment -name FITTER_EFFORT "STANDARD FIT"'
            auto='set_global_assignment -name FITTER_EFFORT "AUTO FIT"'
            if standard in before and standard in after:
                if auto in before and before.index(auto)>before.index(standard):raise ValueError('Fitter effort order changed')
                before=[line for line in before if line!=auto]
        elif rel=='src/fpga/apf/build_id.mif':
            pattern=rb'(?m)^(   0E[012] : )[0-9a-fA-F]{8};$'
            before,after=(re.sub(pattern,rb'\g<1>00000000;',raw.replace(b'\r\n',b'\n')) for raw in (before,after))
        if before!=after:raise ValueError('Compiled source mismatch: '+rel)
        checked[rel]=sha(compiled/rel)
    rbf=outputs/'ap_core.rbf'
    reverse=bytes(int(f'{value:08b}'[::-1],2) for value in range(256))
    binary=rbf.read_bytes().translate(reverse)
    core=out/'core/Cores/pocketlab.WSCoverFlow'
    core.mkdir(parents=True)
    original=candidate/'dist/Cores/agg23.WonderSwan'
    for name in ('core.json','audio.json','input.json','interact.json','video.json','data.json','variants.json'):
        shutil.copy2(original/name,core/name)
    (core/'wswan.rbf_r').write_bytes(binary)
    meta=json.loads((core/'core.json').read_text())
    meta['core']['metadata'].update(platform_ids=['wsclab','wonderswan'],author='pocketlab',shortname='WSCoverFlow',
        url='https://github.com/Sanssssssssssssssss/analogue-pocket-menu-cn',
        description='Chinese CoverFlow. L+R+Select pause. Candidate.')
    meta['core']['cores']=[{'name':'default','id':0,'filename':'wswan.rbf_r'}]
    write(core/'core.json',json.dumps(meta,indent=2)+'\n')
    limits={100:0x10000000,0:0x1000000,9:4096,10:8192,11:524300}
    data=json.loads((core/'data.json').read_text())
    for slot in data['data']['data_slots']:
        slot['size_maximum']=hex(limits[slot['id']])
        if slot['id'] in (9,10):slot['parameters']='0x8'
    write(core/'data.json',json.dumps(data,indent=2)+'\n')
    apf=load('ws_apf_check',ROOT/'tools/apf_metadata.py')
    apf.check_core(core)
    apf.check_candidate_bitstream(core/'wswan.rbf_r')
    platform=out/'core/Platforms';(platform/'_images').mkdir(parents=True)
    definition=json.loads((candidate/'dist/Platforms/wonderswan.json').read_text())
    definition['platform'].update(category='CN Menu',name='WonderSwan CN')
    write(platform/'wsclab.json',json.dumps(definition,indent=2)+'\n')
    shutil.copy2(candidate/'dist/Platforms/_images/wonderswan.bin',platform/'_images/wsclab.bin')
    shutil.copytree(candidate,out/'sources')
    for rel in checked:shutil.copy2(compiled/rel,out/'sources'/rel)
    shutil.copy2(build/'sram-io.tsv',out/'sram-io.tsv')
    shutil.copy2(build/'sram-proof.json',out/'sram-proof.json')
    if validation:
        shutil.copy2(validation_path,out/'validation.json')
        for name in validation['evidence']:
            target=out/'evidence'/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(WORK/name,target)
    sources=out/'source-hashes.json';write(sources,json.dumps(checked,indent=2)+'\n')
    files=[{'path':p.relative_to(out/'core').as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
           for p in sorted((out/'core').rglob('*')) if p.is_file()]
    result={'platform':'wonderswan','version':'0.1.0-ws.1','hardware_acceptance':'pending',
        'core':'pocketlab.WSCoverFlow','namespace':'wsclab','menu_format':'GBAF2/wonderswan',
        'source_inputs':checked,'timing_records':len(timings),'features':[],
        'pause_save_return':True,'bitstream_sha256':sha(core/'wswan.rbf_r'),
        'timing_checks':len(timings),'minimum_slack_ns':min(float(t[1]) for t in timings),
        'critical_warnings':critical,'sram_io':sram,'source_files_checked':len(checked),
        'compiled_rbf_sha256':sha(rbf),'reverse_rbf_sha256':sha(core/'wswan.rbf_r'),
        'source_hash_manifest_sha256':sha(sources),'sram_report_sha256':sha(out/'sram-io.tsv'),
        'sram_proof_sha256':sha(out/'sram-proof.json'),
        'validation_sha256':sha(out/'validation.json') if validation else None,
        'native_saves':'SRAM/EEPROM payload + 12-byte RTC; isolated content-hash names; original saves not imported',
        'files':files}
    write(out/'build-receipt.json',json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('candidate','build','out'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(package(args.candidate,args.build,args.out),indent=2))
