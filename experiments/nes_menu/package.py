#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage a native NES preview only after source, fit and multi-corner timing checks."""
import argparse,hashlib,importlib.util,json,re,shutil,subprocess,sys,uuid
from pathlib import Path
from prepare_build import prepare,ARCHIVE_SHA
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from apf_metadata import check_core
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stage(build,out,archive,coverflow=False):
    build,out=Path(build).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(build) or build.is_relative_to(out):raise ValueError('Fresh staging outside build tree required')
    output=build/'projects/output_files';name='nes_pocket'
    fit=(output/(name+'.fit.summary')).read_text();timing=(output/(name+'.sta.summary')).read_text()
    flow=(output/(name+'.flow.rpt')).read_text()
    slack=[float(v) for v in re.findall(r'Slack\s*:\s*(-?[\d.]+)',timing)]
    tns=[float(v) for v in re.findall(r'TNS\s*:\s*(-?[\d.]+)',timing)]
    if 'Fitter Status : Successful' not in fit or not re.search(r'Flow Status\s*[;:]\s*Successful',flow):raise ValueError('Incomplete compilation')
    if len(slack)<40 or min(slack)<0 or len(tns)!=len(slack) or any(tns):raise ValueError('Incomplete/failing multi-corner timing')
    raw=(output/(name+'.rbf')).read_bytes()
    if not 1024**2<=len(raw)<=3*1024**2 or len(raw)%4:raise ValueError('Unexpected RBF size')
    prepare_inputs=prepare
    if coverflow:
        spec=importlib.util.spec_from_file_location('nes_coverflow_prepare',ROOT/'experiments/nes_coverflow/prepare.py')
        adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter);prepare_inputs=adapter.prepare
    reference=prepare_inputs(archive,ROOT/'.work/nes-menu'/('package-reference-'+uuid.uuid4().hex))
    inputs={}
    for p in reference.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(reference);q=build/rel
        if not q.is_file():raise ValueError('Missing compiled source: '+rel.as_posix())
        a,b=p.read_bytes(),q.read_bytes()
        if p.suffix=='.qsf':
            def settings(x):return [s for s in x.decode().splitlines() if not s.startswith('set_global_assignment -name LAST_QUARTUS_VERSION ')]
            a,b=settings(a),settings(b)
        if a!=b:raise ValueError('Compiled inputs differ from current preparation: '+rel.as_posix())
        inputs[rel.as_posix()]=sha(q)
    pkg=out/'core';dst=pkg/'Cores/pocketlab.NES';dst.mkdir(parents=True)
    original=build/'pkg/pocket/Cores/agg23.NES'
    for key in ['input','interact','audio','video']:shutil.copy2(original/(key+'.json'),dst/(key+'.json'))
    meta=json.loads((original/'core.json').read_text())['core']
    version='0.3.0-nes.2' if coverflow else '0.3.0-nes.1'
    meta['metadata'].update(platform_ids=['neslab','nes'],shortname='NES',author='pocketlab',
        description='Chinese NES preview. L+R+Select: pause, save and return.',
        version=version,date_release='2026-11-02' if coverflow else '2026-11-01',url='https://github.com/Sanssssssssssssssss/analogue-pocket-menu-cn')
    meta['framework']['sleep_supported']=False
    meta['cores']=[{'name':'default','id':0,'filename':'nes.rbf_r'}]
    (dst/'core.json').write_text(json.dumps({'core':meta},indent=2)+'\n')
    if coverflow:
        video=json.loads((dst/'video.json').read_text())
        if len(video['video']['scaler_modes'])!=4:raise ValueError('Inherited scaler slots differ')
        video['video']['scaler_modes'].append({'width':320,'height':288,'aspect_w':10,'aspect_h':9,'rotation':0,'mirror':0})
        (dst/'video.json').write_text(json.dumps(video,indent=2)+'\n')
    slots=[{'id':100,'name':'Chinese Menu','required':True,'deferload':True,'parameters':'0x8','filename':'menu.bin','extensions':['bin'],'address':'0x70000000','size_maximum':'0x10000000'},
        {'id':0,'name':'Cartridge','required':False,'deferload':True,'parameters':'0x8','extensions':['nes'],'address':'0x10000000','size_maximum':'0x2000000'},
        {'id':10,'name':'Save','required':False,'deferload':True,'parameters':'0x0','nonvolatile':True,'extensions':['sav'],'address':'0x20000000','size_maximum':'0x40000'},
        {'id':11,'name':'Custom Palette','required':False,'filename':'palettes/custom.pal','parameters':'0x3','extensions':['pal'],'size_maximum':'0xC0','address':'0x10000000'}]
    (dst/'data.json').write_text(json.dumps({'data':{'magic':'APF_VER_1','data_slots':slots}},indent=2)+'\n')
    table=bytes(int(f'{i:08b}'[::-1],2) for i in range(256));(dst/'nes.rbf_r').write_bytes(raw.translate(table))
    check_core(dst);platforms=pkg/'Platforms';(platforms/'_images').mkdir(parents=True)
    (platforms/'neslab.json').write_text(json.dumps({'platform':{'category':'Console','name':'FC Menu CN','manufacturer':'Pocket Lab','year':2026}},indent=2)+'\n')
    shutil.copy2(build/'pkg/pocket/Platforms/_images/nes.bin',platforms/'_images/neslab.bin')
    limitations=['Memories/sleep disabled','New isolated 256 KiB progress; no automatic save import']
    limitations+=['Native video clock gives approximately 47.85 Hz menu; physical scaler/animation acceptance pending'] if coverflow else ['Static menu transition; animation not accepted']
    receipt={'core':'pocketlab.NES','version':version,'hardware_acceptance':'pending',
        'coverflow_candidate':coverflow,'menu_format':'GBAF2/NES' if coverflow else 'GBAF1/NES',
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'upstream_archive_sha256':ARCHIVE_SHA,'upstream_commit':'be5f1303a0df15d012155cb248b6174bb81e64b6',
        'minimum_slack_ns':min(slack),'timing_records':len(slack),'fit':fit,'timing':timing,
        'timing_scope':'Inherited board/clock constraints; no unconstrained clocks, external port exceptions retained. Not board-level signoff.',
        'limitations':limitations,
        'source_inputs':inputs,'files':[{'path':p.relative_to(pkg).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(pkg.rglob('*')) if p.is_file()]}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['build','out','archive']:p.add_argument('--'+k,required=True)
    p.add_argument('--coverflow',action='store_true')
    a=p.parse_args();r=stage(a.build,a.out,a.archive,a.coverflow);print(json.dumps({k:r[k] for k in ['core','minimum_slack_ns','timing_records','hardware_acceptance']}))
