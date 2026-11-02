#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package one native Sega candidate after input, fit and timing verification."""
import argparse,datetime,hashlib,json,re,shutil,subprocess,sys,uuid
from pathlib import Path
from prepare import prepare,ARCHIVE_SHA,COMMIT
from controller import ROOT,PROFILES
sys.path.insert(0,str(ROOT/'tools'))
from apf_metadata import check_core
from display_styles import configure as configure_display


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def powerup_review(report):
    """Only inherited declaration initializers dominated by explicit reset."""
    expected={'display_on':'Low','irq_line_en':'High','reset_flags':'High','mask_column0':'High'}
    for stem,bits in [('spr_address',range(7)),('bg_address',(1,2,3)),('gg_pdr',range(7)),('jang_bank2',(0,)),('jang_bank4',(0,))]:
        expected.update({f'{stem}[{bit}]':'High' for bit in bits})
    rows=[]
    for line in report.splitlines():
        if 'Critical Warning (' not in line:continue
        if re.search(r'Critical Warning \(18061\): Ignored Power-Up Level option',line):continue
        match=re.search(r'Critical Warning \(18010\): Register [^\n]*\|([^| ]+) will power up to (High|Low)',line)
        if not match or expected.get(match[1])!=match[2]:raise ValueError('Unreviewed critical warning: '+line.strip())
        rows.append({'register':match[1],'powerup':match[2]})
    if not rows:raise ValueError('Expected inherited power-up warning review missing')
    if len({x['register'] for x in rows})!=len(rows):raise ValueError('Duplicate power-up warning records')
    return rows


def build_id_content(raw):
    text=raw.decode('ascii');values={}
    for key in ('0E0','0E1','0E2'):
        matches=re.findall(r'(?m)^(\s*'+key+r'\s*:\s*)([0-9a-fA-F]{8})(;\s*)$',text)
        if len(matches)!=1:raise ValueError('Build identity MIF shape differs')
        values[key]=matches[0][1]
        text=re.sub(r'(?m)^(\s*'+key+r'\s*:\s*)[0-9a-fA-F]{8}(;\s*)$',r'\g<1>00000000\g<2>',text)
    # Only generated date/time/nonce are allowed to differ from the archive.
    return text.replace('\r\n','\n'),values


def stage(build,out,archive,gba_source,platform):
    build,out=Path(build).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(build) or build.is_relative_to(out):raise ValueError('Fresh staging outside build tree required')
    namespace,slot,address,_=PROFILES[platform];short={'gg':'GG','sms':'SMS','sg1000':'SG1000'}[platform]
    output=build/'projects/output_files';name='gg_pocket'
    fit=(output/(name+'.fit.summary')).read_text();timing=(output/(name+'.sta.summary')).read_text()
    flow=(output/(name+'.flow.rpt')).read_text();map_report=(output/(name+'.map.rpt')).read_text(encoding='latin1')
    slack=[float(v) for v in re.findall(r'Slack\s*:\s*(-?[\d.]+)',timing)]
    tns=[float(v) for v in re.findall(r'TNS\s*:\s*(-?[\d.]+)',timing)]
    if 'Fitter Status : Successful' not in fit or not re.search(r'Flow Status\s*[;:]\s*Successful',flow):raise ValueError('Incomplete compilation')
    if len(slack)<60 or min(slack)<0 or len(tns)!=len(slack) or any(tns):raise ValueError('Incomplete/failing multi-corner timing')
    for corner in ('Slow 1100mV 85C','Slow 1100mV 0C','Fast 1100mV 85C','Fast 1100mV 0C'):
        if corner not in timing:raise ValueError('Missing timing corner: '+corner)
    # Other compilation stages must also have no unknown critical warnings.
    warning_rows=powerup_review(map_report)
    if len(warning_rows)!=(23 if platform=='gg' else 16):raise ValueError('Inherited power-up warning set differs')
    for suffix in ('fit.rpt','sta.rpt','asm.rpt'):
        if b'Critical Warning (' in (output/(name+'.'+suffix)).read_bytes():raise ValueError('Unreviewed '+suffix+' critical warning')
    raw=(output/(name+'.rbf')).read_bytes()
    if not 1024**2<=len(raw)<=3*1024**2 or len(raw)%4:raise ValueError('Unexpected RBF size')
    reference=prepare(archive,gba_source,ROOT/'.work/sega-menu'/('package-reference-'+uuid.uuid4().hex),platform)
    inputs={};generated={}
    for p in reference.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(reference);q=build/rel
        if not q.is_file():raise ValueError('Missing compiled input: '+rel.as_posix())
        a,b=p.read_bytes(),q.read_bytes()
        if p.suffix=='.qsf':
            def settings(x):return [s for s in x.decode().splitlines() if not s.startswith('set_global_assignment -name LAST_QUARTUS_VERSION ')]
            a,b=settings(a),settings(b)
        elif rel.as_posix()=='platform/pocket/build_id.mif':
            a,_=build_id_content(a);b,values=build_id_content(b)
            datetime.datetime.strptime(values['0E0']+values['0E1'][2:],'%Y%m%d%H%M%S')
            generated[rel.as_posix()]={'sha256':sha(q),'values':values,'scope':'Upstream PRE_FLOW generated date, time and nonce only'}
        elif p.suffix in ('.json','.qip'):
            a,b=a.replace(b'\r\n',b'\n'),b.replace(b'\r\n',b'\n')
        if a!=b:raise ValueError('Compiled input differs from current preparation: '+rel.as_posix())
        inputs[rel.as_posix()]=sha(q)
    pkg=out/'core';dst=pkg/('Cores/pocketlab.'+short);dst.mkdir(parents=True)
    original=build/('pkg/Cores/kroy.'+short)
    for key in ('input','audio'):shutil.copy2(original/(key+'.json'),dst/(key+'.json'))
    meta=json.loads((original/'core.json').read_text())['core'];version='0.4.0-'+platform+'.1'
    meta['metadata'].update(platform_ids=[namespace,platform],shortname=short,author='pocketlab',
        description='Chinese CoverFlow. L+R+Select: pause, save and return.',version=version,date_release='2026-11-02',
        url='https://github.com/Sanssssssssssssssss/analogue-pocket-menu-cn')
    meta['framework']['sleep_supported']=False
    # Official legacy encoding for bit31: leave physical cartridge power off.
    meta['framework']['hardware']['cartridge_adapter']=-1
    meta['cores']=[{'name':'default','id':0,'filename':platform+'.rbf_r'}]
    def write(name,value):
        (dst/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8',newline='\n')
    write('core',{'core':meta})
    # The native core emits slots 0..3 even in GG mode. UI uses 4 and 5.
    video=json.loads((build/'pkg/Cores/kroy.SMS/video.json').read_text())
    if len(video['video']['scaler_modes'])!=4:raise ValueError('Inherited native scalers differ')
    for w,h,aw,ah in [(320,288,10,9),(256,240,16,15)]:
        video['video']['scaler_modes'].append(dict(width=w,height=h,aspect_w=aw,aspect_h=ah,rotation=0,mirror=0))
    write('video',configure_display(video,platform))
    interact=json.loads((original/'interact.json').read_text());found=0
    for variable in interact['interact']['variables']:
        if int(variable['address'],16)==0xf0000108:
            variable['defaultval']='0x00000001';found+=1
    if found!=1:raise ValueError('Native cheat master control differs')
    write('interact',interact)
    slots=[{'id':100,'name':'Chinese Menu','required':True,'deferload':True,'parameters':'0x8','filename':'menu.bin','extensions':['bin'],'address':'0x70000000','size_maximum':'0x10000000'},
        {'id':slot,'name':'Cartridge','required':False,'deferload':True,'parameters':'0x8','extensions':{'gg':['gg'],'sms':['sms'],'sg1000':['sg','sg1','bin']}[platform],'address':f'0x{address:08X}','size_maximum':'0x400000'},
        {'id':2,'name':'Save','required':False,'deferload':True,'parameters':'0x0','nonvolatile':True,'extensions':['sav'],'address':'0x20000000','size_maximum':'0x8000'},
        {'id':3,'name':'Cheats','required':False,'deferload':True,'parameters':'0x200','extensions':['cht'],'address':'0x50000000','size_maximum':'0x10000'}]
    write('data',{'data':{'magic':'APF_VER_1','data_slots':slots}})
    table=bytes(int(f'{i:08b}'[::-1],2) for i in range(256));(dst/(platform+'.rbf_r')).write_bytes(raw.translate(table));check_core(dst)
    platforms=pkg/'Platforms';(platforms/'_images').mkdir(parents=True)
    (platforms/(namespace+'.json')).write_text(json.dumps({'platform':{'category':'Handheld' if platform=='gg' else 'Console','name':short+' Menu CN','manufacturer':'Pocket Lab','year':2026}},indent=2)+'\n',encoding='utf8',newline='\n')
    shutil.copy2(build/('pkg/Platforms/_images/'+platform+'.bin'),platforms/('_images/'+namespace+'.bin'))
    receipt={'core':'pocketlab.'+short,'platform':platform,'namespace':namespace,'version':version,'menu_format':'GBAF2/Sega',
        'hardware_acceptance':'pending','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'upstream_commit':COMMIT,'upstream_archive_sha256':ARCHIVE_SHA,'minimum_slack_ns':min(slack),'timing_records':len(slack),
        'fit':fit,'timing':timing,'reviewed_powerup_warnings':warning_rows,'generated_metadata_inputs':generated,'source_inputs':inputs,
        'timing_scope':'Inherited constraints and external interface exceptions; behavioral CellRAM model; not board-level signoff',
        'limitations':['Physical game/audio/scaler/cheat/save acceptance pending','Memories/sleep and cartridge play disabled in this independent entry','New isolated 32 KiB saves; no guessed import','Native 5.369 MHz video gives approximately 47.85 Hz menu'],
        'files':[{'path':p.relative_to(pkg).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(pkg.rglob('*')) if p.is_file()]}
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8',newline='\n');return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('build','out','archive','gba-source'):parser.add_argument('--'+key,required=True)
    parser.add_argument('--platform',choices=PROFILES,required=True);args=parser.parse_args()
    result=stage(args.build,args.out,args.archive,args.gba_source,args.platform)
    print(json.dumps({key:result[key] for key in ('core','version','minimum_slack_ns','timing_records','hardware_acceptance')}))
