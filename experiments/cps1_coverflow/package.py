#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package fully fitted native CPS1 and CPS1.5 Chinese CoverFlow candidates."""
import argparse,hashlib,importlib.util,json,re,shutil,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('cps_family_package_prepare',HERE/'prepare.py')
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
sys.path.insert(0,str(ROOT/'tools'))
from apf_metadata import check_core,check_candidate_bitstream
from platform_frontend import encode
import build_library as art
from PIL import Image,ImageDraw

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def normalized_qsf(p):
    # Quartus removes these three duplicated, identical native assignments.
    # Preserve the last occurrence and every other setting, including SEED.
    duplicates={'set_instance_assignment -name WEAK_PULL_UP_RESISTOR ON -to spi_ss',
        'set_global_assignment -name VERILOG_MACRO "POCKET=1"',
        'set_global_assignment -name SEARCH_PATH "../hdl"'}
    rows=p.read_text().splitlines();seen=set();out=[]
    for line in reversed(rows):
        if line.startswith('set_global_assignment -name LAST_QUARTUS_VERSION '):continue
        if line in duplicates:
            if line in seen:continue
            seen.add(line)
        out.append(line)
    return '\n'.join(reversed(out))
def stage(platform,build,prepared_source,native_core,out):
    core,namespace,name=adapter.PROFILES[platform]
    build,prepared_source,native_core,out=map(lambda p:Path(p).resolve(),(build,prepared_source,native_core,out))
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh private output required')
    preparation=json.loads((build/'cps-preparation.json').read_text())
    if preparation['platform']!=platform or preparation['source_commit']!=adapter.COMMIT:raise ValueError('Source identity differs')
    sources={}
    qsf=f'cores/{core}/pocket/jt{core}.qsf'
    for rel,expected in preparation['inputs'].items():
        actual=build/rel
        if not actual.is_file():raise ValueError('Compiled input missing '+rel)
        if sha(actual)!=expected:
            if sha(prepared_source/rel)!=expected:raise ValueError('Prepared source changed '+rel)
            if rel==qsf:
                if normalized_qsf(actual)!=normalized_qsf(prepared_source/rel):raise ValueError('Compiled QSF changed')
            elif rel==f'cores/{core}/pocket/jt{core}.qpf':
                # The pinned upstream generator leaves its QPF template in
                # place. Quartus records the explicitly compiled real revision
                # and refreshes version/date/comments without touching HDL.
                before=[s.strip() for s in (prepared_source/rel).read_text().splitlines() if s.strip() and not s.lstrip().startswith('#')]
                if before!=['QUARTUS_VERSION = "13.1"','DATE = "${DATE}"','PROJECT_REVISION = "jt${CORENAME}"']:
                    raise ValueError('Unexpected upstream QPF template')
                lines=[s.strip() for s in actual.read_text().splitlines() if s.strip() and not s.lstrip().startswith('#')]
                if len(lines)!=4 or lines[0]!='QUARTUS_VERSION = "22.1"' or not lines[1].startswith('DATE = "') or set(lines[2:])!={f'PROJECT_REVISION = "jt{core}"','PROJECT_REVISION = "jt${CORENAME}"'}:
                    raise ValueError('Unexpected QPF rewrite')
            else:raise ValueError('Compiled source changed '+rel)
        sources[rel]=sha(actual)
    reports=build/f'cores/{core}/pocket';revision='jt'+core
    def report(kind):return (reports/f'{revision}.{kind}').read_text(encoding='latin1')
    fit,sta,flow=report('fit.summary'),report('sta.summary'),report('flow.rpt')
    slack=[float(x) for x in re.findall(r'Slack\s*:\s*(-?[\d.]+)',sta)]
    tns=[float(x) for x in re.findall(r'TNS\s*:\s*(-?[\d.]+)',sta)]
    if 'Fitter Status : Successful' not in fit or not re.search(r'Flow Status\s*[;:]\s*Successful',flow):raise ValueError('Full fitting required')
    if len(slack)<100 or min(slack)<0 or len(tns)!=len(slack) or any(tns):raise ValueError('Timing failed or incomplete')
    if any(x not in sta for x in ('Slow 1100mV 85C','Slow 1100mV 0C','Fast 1100mV 85C','Fast 1100mV 0C')):raise ValueError('Missing corner')
    accepted_warnings=[]
    for kind in ('map.rpt','fit.rpt','sta.rpt','asm.rpt'):
        for line in report(kind).splitlines():
            if 'Critical Warning (' not in line:continue
            known=re.search(r'\(127005\): Memory depth \(2048\).*depth \(1280\).*native_pause_pixels_.*\.hdl\.mif',line)
            known=known or (platform=='jtcps1' and re.search(r'\(127005\): Memory depth \(64\).*depth \(49\).*jt6295_adpcm_.*\.hdl\.mif',line))
            if not known:raise ValueError('Unreviewed critical warning '+line.strip())
            accepted_warnings.append(line.strip())
    sta_full=report('sta.rpt')
    unconstrained=[]
    for line in sta_full.splitlines():
        if '; Base' in line and '; Unconstrained' in line:unconstrained.append(line.split(';')[1].strip())
    allowed=('aud_mclk_divider[1]','pck_rgb_clk','pck_rgb_clkq')
    if len(unconstrained)!=3 or any(not any(x.endswith('|'+suffix) for suffix in allowed) for x in unconstrained):raise ValueError('Unexpected native clock scope')
    raw=(reports/f'{revision}.rbf').read_bytes()
    if not 1024**2<len(raw)<3*1024**2 or len(raw)%4:raise ValueError('Bitstream size differs')
    metadata_lock=json.loads((HERE/'metadata-lock.json').read_text())[platform]
    for filename,digest in metadata_lock.items():
        if sha(native_core/filename)!=digest:raise ValueError('Native metadata differs: '+filename)
    files=out/'core';target=files/f'Cores/pocketlab.{name}';target.mkdir(parents=True)
    def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    meta=json.loads((native_core/'core.json').read_text())
    version=f'0.1.0-{core}.1'
    meta['core']['metadata'].update(platform_ids=[namespace,platform,'jtpatreon'],shortname=name,author='pocketlab',
        description='Chinese CoverFlow. L+R+Select opens pause.',url='https://github.com/Sanssssssssssssssss/analogue-pocket-menu-cn',version=version,date_release='2026-11-15')
    meta['core']['framework'].pop('chip32_vm',None);meta['core']['framework']['sleep_supported']=False
    meta['core']['cores']=[{'name':'default','id':0,'filename':platform+'.rbf_r'}]
    write(target/'core.json',meta)
    crt=json.loads((native_core/'data.json').read_text())['data']['data_slots'][-1]
    if crt['id']!=18 or crt['filename']!='crtcfg.bin':raise ValueError('Native CRT slot differs')
    crt['parameters']='0x02000000'
    slots=[{'id':100,'name':'Chinese Menu','required':True,'deferload':True,'parameters':'0x8','filename':'menu.bin','extensions':['bin'],'address':'0x70000000','size_maximum':'0x10000000'},
           {'id':1,'name':'ROM','required':False,'deferload':True,'parameters':'0x8','extensions':['rom'],'address':'0x0','size_maximum':'0x4000000'},
           {'id':2,'name':'Save','required':False,'deferload':True,'parameters':'0x0','extensions':['sav'],'address':'0x0','size_maximum':'0x80','nonvolatile':True},crt]
    write(target/'data.json',{'data':{'magic':'APF_VER_1','data_slots':slots}})
    for filename in ('audio.json','input.json','interact.json','variants.json','video.json'):
        shutil.copy2(native_core/filename,target/filename)
    (target/(platform+'.rbf_r')).write_bytes(raw.translate(bytes(int(f'{i:08b}'[::-1],2) for i in range(256))))
    check_core(target);binary_hash=check_candidate_bitstream(target/(platform+'.rbf_r'))
    platform_dir=files/'Platforms';(platform_dir/'_images').mkdir(parents=True)
    write(platform_dir/(namespace+'.json'),{'platform':{'category':'CN Menu','name':name.replace('15','1.5')+' Menu CN','manufacturer':'Pocket Lab','year':2026}})
    image=Image.new('L',(521,165),0);draw=ImageDraw.Draw(image)
    draw.polygon([(35,15),(133,15),(138,91),(155,145),(20,145),(42,90)],outline=220,width=3)
    draw.rectangle((50,30,119,82),outline=160,width=3);draw.line((67,100,67,116),fill=230,width=4)
    draw.ellipse((61,94,73,106),fill=230)
    for x,y in ((96,105),(113,99),(130,105)):draw.ellipse((x-3,y-3,x+3,y+3),fill=190)
    for title,y,scale in ((name.replace('15','1.5'),40,3),('中文游戏菜单',104,2)):
        width,pixels,clipped,missing=art.columns(title,art.font())
        if clipped or missing:raise ValueError('Missing platform glyph')
        glyph=Image.new('L',(width,16));g=ImageDraw.Draw(glyph)
        for x,column in enumerate(struct.unpack('<512H',pixels)[:width]):
            for row in range(16):
                if column>>row&1:g.point((x,row),fill=235)
        image.paste(glyph.resize((width*scale,16*scale),Image.Resampling.NEAREST),(184,y))
    (platform_dir/'_images'/(namespace+'.bin')).write_bytes(encode(image));image.save(out/'platform.png')
    licenses=target/'licenses';licenses.mkdir();shutil.copy2(build/'LICENSE',licenses/'JTcores-GPL-3.0.txt')
    (licenses/'SOURCES.txt').write_text('Native engine: https://github.com/jotego/jtcores\nCommit: '+adapter.COMMIT+'\nNative cores, JTFRAME, fx68k, JT51 and JT6295/JTDSP16 retain their original licenses.\nMenu additions: experiments/cps1_coverflow and shared CoverFlow modules, MIT.\nAPF and Intel files retain their original notices.\n',encoding='ascii')
    for rel in list(sources):
        dest=out/'sources'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(build/rel,dest)
    for filename,digest in metadata_lock.items():
        rel=f'native_metadata/{platform}/{filename}';dest=out/'sources'/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(native_core/filename,dest);sources[rel]=digest
    shutil.copy2(HERE/'TIMING.md',out/'TIMING.md')
    receipt={'platform':platform,'core':'pocketlab.'+name,'namespace':namespace,'menu_format':'GBAF2/'+platform,'version':version,
        'source_repo':'https://github.com/jotego/jtcores','source_commit':adapter.COMMIT,'source_inputs':sources,
        'base_receipt_sha256':preparation['base_receipt_sha256'],'fit':fit,'timing_records':len(slack),'minimum_slack_ns':min(slack),
        'bitstream_sha256':binary_hash,'hardware_acceptance':'pending','category':'CN Menu','pause_save_return':True,
        'save_support':'Native 128-byte EEPROM; original byte layout preserved; isolated identity per ROM and instance settings; no save states or sleep.',
        'timing_scope':'Four-corner STA for constrained paths. Inherited DDR video output clocks, I2S divider and native external I/O delays remain outside that proof.',
        'native_unconstrained_clocks':unconstrained,'accepted_initialization_warnings':accepted_warnings,'original_game_scaler_preserved':True,
        'files':[{'path':p.relative_to(files).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files.rglob('*')) if p.is_file()]}
    write(out/'build-receipt.json',receipt);return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('platform',choices=adapter.PROFILES)
    for key in ('build','prepared-source','native-core','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();r=stage(a.platform,a.build,a.prepared_source,a.native_core,a.out)
    print(json.dumps({k:r[k] for k in ('core','version','timing_records','minimum_slack_ns','bitstream_sha256')}))
