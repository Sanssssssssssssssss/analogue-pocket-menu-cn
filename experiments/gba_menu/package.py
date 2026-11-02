#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage an independent GBA menu core after full fit and timing have passed."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import uuid
import sys
from prepare_build import prepare

ROOT=Path(__file__).resolve().parents[2]
CORE='pocketlab.GBA'
sys.path.insert(0,str(ROOT/'tools'))
from apf_metadata import check_core


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def stage(build,out,sources,motion=False,coverflow=False):
    if motion and coverflow:raise ValueError('Select one experimental renderer')
    build,out=Path(build).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(build):raise ValueError('Use fresh staging outside build tree')
    files=build/'src/fpga/build/output_files'
    fit=(files/'ap_core.fit.summary').read_text(encoding='utf-8')
    timing=(files/'ap_core.sta.summary').read_text(encoding='utf-8')
    flow=(files/'ap_core.flow.rpt').read_text(encoding='utf-8')
    if not re.search(r'Fitter Status\s*:\s*Successful',fit) or not re.search(r'Flow Status\s*[;:]\s*Successful',flow):
        raise ValueError('Full compilation and fitting must pass')
    slack=[float(v) for v in re.findall(r'Slack\s*:\s*(-?[\d.]+)',timing)]
    tns=[float(v) for v in re.findall(r'TNS\s*:\s*(-?[\d.]+)',timing)]
    if len(slack)<40 or min(slack)<0 or not tns or any(tns):raise ValueError('Incomplete or failing multi-corner timing')
    bios=(build/'src/fpga/gba/gba_bios.vhd').read_text(encoding='utf-8')
    if "signal rom : t_rom := (others => (others => '0'));" not in bios:
        raise ValueError('Embedded BIOS has not been removed')
    raw=(files/'ap_core.rbf').read_bytes()
    # Cyclone V RBF size varies with fitted memory/configuration contents.
    if not 1024**2<=len(raw)<=3*1024**2 or len(raw)%4:
        raise ValueError('Unexpected GBA Pocket bitstream size')
    # Recreate all inputs from the pinned source plus current integration script.
    # Checking only the two new menu modules would miss stale lifecycle wiring.
    reference_path=ROOT/'.work/gba-menu'/('package-reference-'+uuid.uuid4().hex)
    if coverflow:
        spec=importlib.util.spec_from_file_location('coverflow_prepare',ROOT/'experiments/gba_coverflow/prepare.py')
        renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
        reference=renderer.prepare(sources,reference_path)
    else:reference=prepare(sources,reference_path,True)
    if motion:
        from prepare_motion import integrate_motion
        integrate_motion(reference)
    for p in (reference/'src').rglob('*'):
        if p.is_file():
            rel=p.relative_to(reference)
            actual,expected=(build/rel).read_bytes(),p.read_bytes()
            if rel.as_posix()=='src/fpga/build/ap_core.qsf':
                # Quartus rewrites this informational version field and line endings.
                def settings(raw):
                    lines=raw.decode('utf-8').splitlines()
                    return [s for s in lines if not s.startswith('set_global_assignment -name LAST_QUARTUS_VERSION ')]
                actual,expected=settings(actual),settings(expected)
            if actual!=expected:
                raise ValueError('Compiled source differs from current integration: '+rel.as_posix())
    pkg=out/'core';dst=pkg/'Cores'/CORE;dst.mkdir(parents=True)
    upstream=build/'pkg/Cores/mincer_ray.GBA'
    for name in ('audio.json','input.json','interact.json','variants.json','video.json'):
        shutil.copy2(upstream/name,dst/name)
    meta=json.loads((upstream/'core.json').read_text())['core']
    version='0.2.0-gba.5' if coverflow else '0.2.0-gba.4' if motion else '0.2.0-gba.3'
    meta['metadata'].update(platform_ids=['gbalab','gba'],shortname='GBA',
        description='Chinese GBA menu. L+R+Select: pause, save and return.',
        author='pocketlab',url='https://github.com/Sanssssssssssssssss/analogue-pocket-menu-cn',
        version=version,date_release='2026-11-02' if coverflow else '2026-11-01' if motion else '2026-10-31')
    meta['framework']['sleep_supported']=False
    meta['cores']=[{'name':'default','id':0,'filename':'gba.rbf_r'}]
    (dst/'core.json').write_text(json.dumps({'core':meta},indent=2)+'\n')
    if coverflow:
        video=json.loads((dst/'video.json').read_text())
        modes=video['video']['scaler_modes']
        if len(modes)!=1 or modes[0]['width']!=240 or modes[0]['height']!=160:raise ValueError('Unexpected inherited game scaler modes')
        modes.append({'width':320,'height':288,'aspect_w':10,'aspect_h':9,'rotation':0,'mirror':0})
        (dst/'video.json').write_text(json.dumps(video,indent=2)+'\n')
    slots=[
        {'id':100,'name':'Chinese Menu','required':True,'deferload':True,'parameters':'0x8',
         'filename':'menu.bin','extensions':['bin'],'address':'0x70000000','size_maximum':'0x10000000'},
        {'id':4,'name':'GBA BIOS','required':True,'parameters':'0x1000008','filename':'gba_bios.bin',
         'extensions':['bin'],'address':'0x30000000','size_exact':16384},
        {'id':1,'name':'Game','required':False,'deferload':True,'parameters':'0x8',
         'extensions':['gba'],'address':'0x10000000','size_maximum':'0x2000000'},
        {'id':10,'name':'Save','required':False,'deferload':True,'parameters':'0x0','nonvolatile':True,
         'extensions':['sav'],'address':'0x20000000','size_maximum':'0x20000'},
        {'id':11,'name':'RTC','required':False,'deferload':True,'parameters':'0x0','nonvolatile':True,
         'extensions':['rtc'],'address':'0x21000000','size_exact':16}]
    (dst/'data.json').write_text(json.dumps({'data':{'magic':'APF_VER_1','data_slots':slots}},indent=2)+'\n')
    table=bytes(int(f'{i:08b}'[::-1],2) for i in range(256))
    (dst/'gba.rbf_r').write_bytes(raw.translate(table))
    interact=json.loads((dst/'interact.json').read_text(encoding='utf8'))
    for label,address,id_ in [('M',0xF4000000,60000),('P',0xF4000004,60003),
                              ('V',0xF4000008,60004),('E',0xF400000C,60005),
                              ('F',0xF4000010,60006),
                              ('T',0xF8001000,60001),('H',0xF8000000,60002)]:
        interact['interact']['variables'].append({'name':label,'id':id_,'type':'number_u32','enabled':False,'address':hex(address)})
    (dst/'interact.json').write_text(json.dumps(interact,indent=2)+'\n',encoding='utf8')
    check_core(dst)
    platforms=pkg/'Platforms';(platforms/'_images').mkdir(parents=True)
    platform={'platform':{'category':'Handheld','name':'GBA Menu CN','manufacturer':'Pocket Lab','year':2026}}
    (platforms/'gbalab.json').write_text(json.dumps(platform,indent=2)+'\n')
    shutil.copy2(build/'pkg/Platforms/_images/gba.bin',platforms/'_images/gbalab.bin')
    # No user BIOS, ROM or progress is ever copied by this packager.
    sources={p.relative_to(build).as_posix():sha(p) for p in (build/'src').rglob('*') if p.is_file() and not any(t in p.parts for t in ('build','db','incremental_db','output_files'))}
    sources['src/fpga/build/ap_core.qsf']=sha(build/'src/fpga/build/ap_core.qsf')
    sources['src/fpga/build/gba_menu_error.hex']=sha(build/'src/fpga/build/gba_menu_error.hex')
    receipt={'core':CORE,'version':version,'hardware_playtest':'pending_coverflow_and_save_return' if coverflow else 'pending_motion_retest' if motion else 'pending_framebuffer_ownership_retest',
             'motion_candidate':motion,
             'coverflow_candidate':coverflow,'menu_format':'GBAF2' if coverflow else 'GBAF1',
             'upstream':json.loads(Path(__file__).with_name('upstream-lock.json').read_text())['commit'],
             'bitstream_sha256':sha(dst/'gba.rbf_r'),'minimum_reported_slack_ns':min(slack),
             'timing_scope':'All inherited multi-corner constraints; board-level exceptions remain as upstream',
             'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             'source_files':sources,'fit':fit,'timing':timing,
             'files':[{'path':p.relative_to(pkg).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(pkg.rglob('*')) if p.is_file()]}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('build','out','sources'):p.add_argument('--'+arg,required=True)
    p.add_argument('--motion',action='store_true',help='Package the separate menu slide candidate')
    p.add_argument('--coverflow',action='store_true',help='Package the shared GB/GBC CoverFlow adapter; requires GBAF2 assets')
    a=p.parse_args()
    try:
        r=stage(a.build,a.out,a.sources,a.motion,a.coverflow);print(json.dumps({k:r[k] for k in ('core','bitstream_sha256','minimum_reported_slack_ns','hardware_playtest')}))
    except (OSError,ValueError) as e:p.exit(2,str(e)+'\n')
