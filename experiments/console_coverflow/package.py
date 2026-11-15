#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage independent native CoverFlow previews from checked full builds."""

import argparse
import json
import re
import shutil
import sys
import uuid
from pathlib import Path

from prepare import ROOT, PROFILES, prepare

sys.path.insert(0,str(ROOT/'tools'))
from apf_metadata import check_candidate_bitstream, check_core
from build_library import sha

BUILDS = {
    'pce': ('projects','pce_pocket','pkg','agg23.PC Engine','PCE','pce',('pce','sgx')),
    'genesis': ('src/fpga','ap_core','dist','ericlewis.Genesis','Genesis','md',('md','gen','bin')),
    'snes': ('projects','snes_pocket','pkg/pocket','agg23.SNES','SNES','sfc',('sfc','smc','bin')),
    'jtcps2': ('cores/cps2/pocket','jtcps2','jtbin/pocket/raw','jotego.jtcps2','CPS2','cps2',('rom',)),
}
CPS2_METADATA = {
    'core.json':'e68ee4ae7d65b35ba375eeced544b6e2d837e519f13872122a39dd0d8f5e3f62',
    'data.json':'9829f60cc39a52b7058ef61aee1878849288e7b274399f1fc6bca00af81338d7',
    'audio.json':'5e2b61c3e0dd6da89d13ea2bcbb06c0ad38d0a8b94035ec2a260e9ddcad17ca5',
    'input.json':'aeda54d96d9184795601574147dba49322b5d9bd14baabd01a62611d41f59d15',
    'interact.json':'1e45d9eb3a6314d8223eead7ee5e09baced4bf80fe55883d8a71c1f1fe6543cb',
    'variants.json':'e043a74f385862c232f52bc333c7b301643f4c75000c4cf7c79de853878e4cd1',
    'video.json':'6b17d4bd80295b7e6fecb4ae12e2d286ff120be517b2c8c7bc3cad9f36657ee8',
}


def inherited_warning(platform, line, pause_save=False):
    if pause_save and re.search(
            r'\(127005\): Memory depth \(2048\).*depth \(1280\).*native_pause_pixels_.*\.hdl\.mif.*remaining addresses to 0', line):
        # Ten labels occupy 1280 words. The remaining addresses are unreachable.
        return True
    if platform=='snes':
        # The original CE accumulator is explicitly asynchronously reset to zero.
        return (line.endswith('(18061): Ignored Power-Up Level option on the following registers')
                or re.search(r'\(18010\): Register .*\|CEGen:CEGen\|CLK_SUM\[(0|31)\] will power up to Low .*CEGen\.vhd',line))
    if platform=='jtcps2':
        # The pinned stock JTFRAME gain table also pads the unused final 24 addresses.
        return re.search(r'\(127005\): Memory depth \(64\).*depth \(40\).*jtcps15_sound_.*\.hdl\.mif.*remaining addresses to 0',line)
    return False


def stage(platform, build, archive, gba_source, out, native_features=False, pause_save=False,
          cps2_base=None, cps2_init_inputs=None):
    build, archive, out = Path(build).resolve(), Path(archive).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work') or out.is_relative_to(build) or build.is_relative_to(out):
        raise ValueError('Fresh separate local staging required')
    project, revision, stock, upstream, name, short, extensions = BUILDS[platform]
    namespace, capacity, maximum, address, archive_sha = PROFILES[platform]
    cps = platform=='jtcps2'
    if pause_save and not (cps or native_features):
        raise ValueError('Pause and save require the native feature source tree')
    outputs = build/project if cps else build/project/'output_files'
    def report(suffix):
        return (outputs/f'{revision}.{suffix}').read_text(encoding='latin1')
    fit, timing, flow = report('fit.summary'), report('sta.summary'), report('flow.rpt')
    slack = [float(v) for v in re.findall(r'Slack\s*:\s*(-?[\d.]+)',timing)]
    tns = [float(v) for v in re.findall(r'TNS\s*:\s*(-?[\d.]+)',timing)]
    if 'Fitter Status : Successful' not in fit or not re.search(r'Flow Status\s*[;:]\s*Successful',flow):
        raise ValueError('Full compilation and fitting must pass')
    corners = ('Slow 1100mV 85C','Slow 1100mV 0C','Fast 1100mV 85C','Fast 1100mV 0C')
    if len(slack)<40 or min(slack)<0 or len(tns)!=len(slack) or any(tns) or any(c not in timing for c in corners):
        raise ValueError('Incomplete or failing multi-corner timing')
    for suffix in ('map.rpt','fit.rpt','sta.rpt','asm.rpt'):
        for line in report(suffix).splitlines():
            if 'Critical Warning (' in line and not inherited_warning(platform,line.strip(),pause_save):
                raise ValueError('Unreviewed critical warning in '+suffix+': '+line.strip())
    raw = (outputs/f'{revision}.rbf').read_bytes()
    if not 1024**2<=len(raw)<=3*1024**2 or len(raw)%4:
        raise ValueError('Unexpected Pocket bitstream length')

    reference_path = ROOT/'.work/console-coverflow'/('package-reference-'+uuid.uuid4().hex)
    if pause_save:
        sys.path.insert(0,str(ROOT/'experiments/native_features'))
        if cps:
            import prepare_cps2_pause
            reference=prepare_cps2_pause.prepare(cps2_base,reference_path,cps2_init_inputs)
        else:
            import prepare_pause
            reference=prepare_pause.prepare(platform,archive,gba_source,reference_path)
    elif native_features:
        if cps:raise ValueError('No native CPS2 cheat adapter is implemented')
        sys.path.insert(0,str(ROOT/'experiments/native_features'))
        import prepare_consoles
        reference=prepare_consoles.prepare(platform,archive,gba_source,reference_path)
    elif cps:
        from cps2_native import COVERFLOW_INPUTS, prepare as prepare_cps2
        reference = prepare_cps2(archive/'jtcores',gba_source,reference_path)
    elif platform=='snes':
        from snes import prepare as prepare_snes
        reference = prepare_snes(archive,reference_path)
    else:
        reference = prepare(archive,gba_source,reference_path,platform)
    sources = {}
    for file in reference.rglob('*'):
        if not file.is_file():
            continue
        rel = file.relative_to(reference)
        if cps and not pause_save:
            if len(rel.parts)>1:
                continue  # Generated bridge staging is checked through the merged files.
            if rel.name.startswith('jtframe_pocket'):
                rel=Path('modules/jtframe/target/pocket/hdl')/rel
            elif rel.name in COVERFLOW_INPUTS or rel.name=='font_cn.hex':
                rel=Path(project)/(rel if rel.name=='font_cn.hex' else Path('coverflow')/rel)
            else:
                continue
        if rel.is_relative_to(Path(project)/'output_files') or {'db','incremental_db'} & set(rel.parts):
            continue
        actual = build/rel
        before, after = file.read_bytes(), actual.read_bytes()
        if rel.as_posix()==f'{project}/{revision}.qsf':
            ignored = ('set_global_assignment -name LAST_QUARTUS_VERSION ', 'set_global_assignment -name SEED ')
            before, after = ([line for line in data.decode().splitlines() if not line.startswith(ignored)] for data in (before,after))
        elif rel.as_posix()=='src/fpga/apf/build_id.mif':
            # Genesis PRE_FLOW changes three identity words and native newlines.
            pattern = rb'(?m)^(   0E[012] : )[0-9a-fA-F]{8};$'
            before, after = (re.sub(pattern,rb'\g<1>00000000;',data.replace(b'\r\n',b'\n')) for data in (before,after))
        if before!=after:
            raise ValueError('Compiled input differs from prepared source: '+rel.as_posix())
        sources[rel.as_posix()] = sha(actual)

    stock_root = archive/stock if cps else reference/stock
    original = stock_root/'Cores'/upstream
    if cps:
        if any(sha(original/name)!=digest for name,digest in CPS2_METADATA.items()):
            raise ValueError('CPS2 original Pocket definitions differ from pinned jtbin')
        if sha(stock_root/'Platforms/_images/jtcps2.bin')!='56a2f181a11b01c8fa83ffc2da9b72b95ab1dc63b9b588b2898b56a7201cb523':
            raise ValueError('CPS2 original platform icon differs from pinned jtbin')
        for rel in (Path(project)/'jtcps2.qsf',Path(project)/'files.qip'):
            sources[rel.as_posix()] = sha(build/rel)
    core_name = f'pocketlab.{name}'
    package = out/'core'
    target = package/'Cores'/core_name
    binary = platform+'.rbf_r'
    meta = json.loads((original/'core.json').read_text(encoding='utf8'))['core']
    meta['metadata'].update(platform_ids=[namespace,platform],shortname=name,author='pocketlab',
        description='Chinese CoverFlow menu. Use Pocket Quit to exit.',version=f'0.1.0-{short}.1',date_release='2026-11-08',
        url='https://github.com/Sanssssssssssssssss/analogue-pocket-menu-cn')
    meta['framework'].pop('chip32_vm',None)
    meta['framework']['sleep_supported'] = False
    meta['cores'] = [{'name':'default','id':0,'filename':binary}]
    video = json.loads((original/'video.json').read_text(encoding='utf8'))
    if len(video['video']['scaler_modes'])!=(8 if cps else 4 if platform=='snes' else 6):
        raise ValueError('Inherited scaler slots differ from the build')
    if not cps:
        video['video']['scaler_modes'].append(dict(width=320,height=288,aspect_w=10,aspect_h=9,rotation=0,mirror=0))
    if platform=='genesis':
        video['video']['display_modes']=[{'id':'0x10'}]
    slots = [
        dict(id=100,name='Chinese Menu',required=True,deferload=True,parameters='0x8',filename='menu.bin',
            extensions=['bin'],address='0x70000000',size_maximum='0x10000000'),
        dict(id=1 if cps else 0,name='ROM' if cps else 'Cartridge',required=False,deferload=True,parameters='0x8',extensions=list(extensions),
            address='0x0' if cps else '0x10000000',size_maximum=hex(maximum)),
        dict(id=2 if cps else 10,name='Save',required=False,deferload=True,parameters='0x0',extensions=['sav'],
            address=hex(address),size_maximum=hex(capacity),nonvolatile=True),
    ]
    if cps:
        crt = json.loads((original/'data.json').read_text(encoding='utf8'))['data']['data_slots'][-1]
        slots.append(crt)
    if native_features:
        slots.append(dict(id=12,name='Matched Cheats',required=False,deferload=True,parameters='0x8',
                          extensions=['cht'],address='0xA0000000',size_maximum='0x130'))
        meta['metadata'].update(version='0.4.0-'+short+'.1',date_release='2026-11-08')
    if pause_save:
        meta['metadata'].update(version='0.4.0-'+short+('.1' if cps else '.2'),
                                description='Chinese CoverFlow. L+R+Select opens pause.')
        if platform in ('snes', 'jtcps2'):
            meta['metadata'].update(version='0.4.0-'+short+'.3',date_release='2026-11-15')
    target.mkdir(parents=True)
    def write(path, data):
        path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf8',newline='\n')
    write(target/'core.json',{'core':meta})
    write(target/'data.json',{'data':{'magic':'APF_VER_1','data_slots':slots}})
    write(target/'video.json',video)
    for filename in ('audio.json','input.json','interact.json','variants.json'):
        shutil.copy2(original/filename,target/filename)
    reverse_bits = bytes(int(f'{i:08b}'[::-1],2) for i in range(256))
    (target/binary).write_bytes(raw.translate(reverse_bits))
    check_core(target)
    check_candidate_bitstream(target/binary)
    platforms = package/'Platforms'
    (platforms/'_images').mkdir(parents=True)
    write(platforms/(namespace+'.json'),{'platform':{'category':'Arcade' if cps else 'Console','name':name+' Menu CN','manufacturer':'Pocket Lab','year':2026}})
    shutil.copy2(stock_root/'Platforms/_images'/(platform+'.bin'),platforms/'_images'/(namespace+'.bin'))
    receipt = {'core':core_name,'namespace':namespace,'menu_format':'GBAF2/SNES' if platform=='snes' else 'GBAF2/'+platform,'minimum_slack_ns':min(slack),
               'timing_records':len(slack),'fit':fit,'timing':timing,'upstream_archive_sha256':archive_sha,'source_inputs':sources,
               'hardware_acceptance':'pending','saves':'isolated ordinary save namespace',
               'exit':'L+R+Select, save and return' if pause_save else 'Pocket OS Quit',
               'files':[{'path':p.relative_to(package).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}
                        for p in sorted(package.rglob('*')) if p.is_file()]}
    if native_features or pause_save:
        receipt.update(features=['PLCH1'] if native_features else [],
                       version=meta['metadata']['version'],bitstream_sha256=sha(target/binary))
        if pause_save:
            receipt['pause_save_return'] = True
        for rel in sources:
            target_source=out/'sources'/rel;target_source.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(build/rel,target_source)
    write(out/'build-receipt.json',receipt)
    return receipt


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('platform',choices=BUILDS)
    for arg in ('build','archive','out'):
        cli.add_argument('--'+arg,type=Path,required=True)
    cli.add_argument('--gba-source',type=Path)
    cli.add_argument('--native-features',action='store_true')
    cli.add_argument('--pause-save',action='store_true')
    cli.add_argument('--cps2-base',type=Path)
    cli.add_argument('--cps2-init-inputs',type=Path)
    args = cli.parse_args()
    receipt = stage(args.platform,args.build,args.archive,args.gba_source,args.out,
                    args.native_features,args.pause_save,args.cps2_base,args.cps2_init_inputs)
    print(json.dumps({key:receipt[key] for key in ('core','minimum_slack_ns','timing_records','hardware_acceptance')}))
