#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package a source-matched, fully fitted Arduboy CN Menu candidate offline."""
import argparse,hashlib,importlib.util,json,re,shutil,struct,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('ard_package_prepare',Path(__file__).with_name('prepare.py'))
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
ROOT,COMMIT,REPO,NAMESPACE=adapter.ROOT,adapter.COMMIT,adapter.REPO,adapter.NAMESPACE
sys.path.insert(0,str(ROOT/'tools'))
from apf_metadata import check_core,check_candidate_bitstream
from platform_frontend import encode
import build_library as art
from PIL import Image,ImageDraw

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def normalized_qsf(raw):return '\n'.join(line for line in raw.decode().splitlines() if not line.startswith('set_global_assignment -name LAST_QUARTUS_VERSION '))
def stage(build,out,prepared_source):
    build,out=Path(build).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh private output required')
    prepared=json.loads((build/'ard-preparation.json').read_text())
    if prepared['source_commit']!=COMMIT:raise ValueError('Source version mismatch')
    sources={}
    for rel,expected in prepared['inputs'].items():
        p=build/rel
        if not p.is_file():raise ValueError('Compiled input missing '+rel)
        if sha(p)!=expected:
            if rel!='src/fpga/ap_core.qsf':raise ValueError('Compiled input changed '+rel)
            # Quartus updates this version line itself. Other settings must be
            # compared against the immutable prepared tree by the caller below.
            candidate=Path(prepared_source).resolve()/rel
            if not candidate.is_file() or sha(candidate)!=expected or normalized_qsf(p.read_bytes())!=normalized_qsf(candidate.read_bytes()):
                raise ValueError('Unexpected QSF change')
        sources[rel]=sha(p)
    for rel in ['src/fpga/apf/build_id.mif','src/fpga/apf/build_id.v']:
        if (build/rel).is_file():sources[rel]=sha(build/rel)
    reports=build/'src/fpga/output_files';revision='ap_core'
    def report(kind):return (reports/f'{revision}.{kind}').read_text(encoding='latin1')
    fit,sta,flow=report('fit.summary'),report('sta.summary'),report('flow.rpt')
    slack=[float(x) for x in re.findall(r'Slack\s*:\s*(-?[\d.]+)',sta)]
    tns=[float(x) for x in re.findall(r'TNS\s*:\s*(-?[\d.]+)',sta)]
    if 'Fitter Status : Successful' not in fit or not re.search(r'Flow Status\s*[;:]\s*Successful',flow):raise ValueError('Full fitting required')
    if len(slack)<40 or min(slack)<0 or len(tns)!=len(slack) or any(tns):raise ValueError('Timing failed or incomplete')
    if any(x not in sta for x in ['Slow 1100mV 85C','Slow 1100mV 0C','Fast 1100mV 85C','Fast 1100mV 0C']):raise ValueError('Missing timing corner')
    for kind in ['map.rpt','fit.rpt','sta.rpt','asm.rpt']:
        if 'Critical Warning (' in report(kind):raise ValueError('Unreviewed critical warning in '+kind)
    if not re.search(r'Unconstrained Clocks\s*;\s*1\s*;\s*1\s*;',report('sta.rpt')):
        raise ValueError('Unexpected unconstrained clock count; only native software OLED SPI may remain')
    raw=(reports/f'{revision}.rbf').read_bytes()
    if not 1024**2<len(raw)<3*1024**2 or len(raw)%4:raise ValueError('Bitstream size')
    files=out/'core';target=files/'Cores/pocketlab.Arduboy';target.mkdir(parents=True)
    original=build/'dist/Cores/agg23.Arduboy'
    def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    meta=json.loads((original/'core.json').read_text())
    meta['core']['metadata'].update(platform_ids=[NAMESPACE,'arduboy'],shortname='Arduboy',author='pocketlab',
        description='Chinese CoverFlow for native Arduboy',url='https://github.com/Sanssssssssssssssss/analogue-pocket-menu-cn',
        version='0.1.0-ard.1',date_release='2026-11-15')
    meta['core']['cores']=[{'name':'default','id':0,'filename':'ard.rbf_r'}]
    meta['core']['framework']['sleep_supported']=False
    write(target/'core.json',meta)
    write(target/'data.json',{'data':{'magic':'APF_VER_1','data_slots':[
        {'id':100,'name':'Chinese Menu','required':True,'deferload':True,'parameters':'0x8','filename':'menu.bin',
         'extensions':['bin'],'address':'0x70000000','size_maximum':'0x10000000'},
        {'id':0,'name':'Cartridge','required':False,'deferload':True,'parameters':'0x8','extensions':['hex'],
         'address':'0x00000000','size_maximum':'0x40000'},
        {'id':10,'name':'EEPROM','required':False,'deferload':True,'nonvolatile':True,'parameters':'0x84',
         'extensions':['sav'],'address':'0x20000000','size_maximum':'0x400'}]}})
    video=json.loads((original/'video.json').read_text())
    if len(video['video']['scaler_modes'])!=1:raise ValueError('Original game scaler changed')
    video['video']['scaler_modes'].append({'width':320,'height':288,'aspect_w':10,'aspect_h':9,'rotation':0,'mirror':0})
    write(target/'video.json',video)
    for name in ['audio.json','input.json','interact.json','variants.json','icon.bin']:
        shutil.copy2(original/name,target/name)
    (target/'info.txt').write_text('Native Arduboy + Chinese CoverFlow.\nGPL3 engine; MIT menu; APF/Intel components retain notices.\nNative 1KiB EEPROM; no states/sleep. Hardware acceptance pending.\n',encoding='ascii')
    (target/'ard.rbf_r').write_bytes(raw.translate(bytes(int(f'{i:08b}'[::-1],2) for i in range(256))))
    check_core(target);bitstream=check_candidate_bitstream(target/'ard.rbf_r')
    platform=files/'Platforms';(platform/'_images').mkdir(parents=True)
    write(platform/(NAMESPACE+'.json'),{'platform':{'category':'CN Menu','name':'Arduboy Menu CN','manufacturer':'Pocket Lab','year':2026}})
    image=Image.new('L',(521,165),0);draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((24,13,138,150),radius=12,outline=220,width=3)
    draw.rectangle((39,28,123,99),outline=160,width=3)
    draw.line((43,123,75,123),fill=200,width=5);draw.line((59,107,59,139),fill=200,width=5)
    draw.ellipse((102,114,115,127),fill=210)
    for title,y,scale in [('Arduboy',42,3),('中文游戏菜单',105,2)]:
        width,raw,clipped,missing=art.columns(title,art.font())
        if missing or clipped:raise ValueError('Missing banner glyph')
        glyph=Image.new('L',(width,16),0);g=ImageDraw.Draw(glyph)
        for x,column in enumerate(struct.unpack('<512H',raw)[:width]):
            for row in range(16):
                if column>>row&1:g.point((x,row),fill=235)
        image.paste(glyph.resize((width*scale,16*scale),Image.Resampling.NEAREST),(175,y))
    (platform/'_images'/(NAMESPACE+'.bin')).write_bytes(encode(image));image.save(out/'platform.png')
    license_dir=target/'licenses';license_dir.mkdir()
    shutil.copy2(build/'LICENSE',license_dir/'Arduboy-GPL-3.0.txt')
    (license_dir/'SOURCES.txt').write_text(f'Native engine: {REPO}\nCommit: {COMMIT}\nMenu additions: experiments/arduboy_coverflow and shared CoverFlow modules in the project source.\nUpstream modules retain GPL2-or-later, GPL3, MIT, APF and Intel notices.\n',encoding='utf8')
    receipt={'platform':'arduboy','core':'pocketlab.Arduboy','namespace':NAMESPACE,
        'menu_format':'GBAF2/arduboy','version':'0.1.0-ard.1',
        'source_repo':REPO,'source_commit':COMMIT,'source_inputs':sources,'fit':fit,
        'timing_records':len(slack),'minimum_slack_ns':min(slack),'bitstream_sha256':bitstream,
        'timing_scope':'Four-corner STA for constrained bridge, menu/video, single-clock I2S and AVR/EEPROM domains; native software OLED SPI remains unconstrained upstream.',
        'native_unconstrained_clocks':['ic|atmega32u4|SPI1.spi_1|SPCR[3]'],
        'audio':'74.25MHz clock enables preserve upstream I2S bit sequence and controls; two AVR buzzer inputs use three-stage CDC before decoding.',
        'hardware_acceptance':'pending','save_support':'Native 1KiB per-ROM EEPROM, initialized FF; original global save untouched; no states or sleep',
        'original_game_scaler_preserved':True,'category':'CN Menu','files':[
            {'path':p.relative_to(files).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}
            for p in sorted(files.rglob('*')) if p.is_file()]}
    for rel in sources:
        destination=out/'sources'/rel;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(build/rel,destination)
    write(out/'build-receipt.json',receipt)
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['build','out','prepared-source']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();r=stage(a.build,a.out,a.prepared_source);print(json.dumps({k:r[k] for k in ['version','timing_records','minimum_slack_ns','bitstream_sha256']}))
