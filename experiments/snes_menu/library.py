#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage standard NTSC SNES favorites using the upstream loader's audited decisions."""
import argparse,base64,hashlib,importlib.util,json,re,subprocess,tempfile,sys
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('nes_library',ROOT/'experiments/nes_menu/library.py')
nes=importlib.util.module_from_spec(spec);spec.loader.exec_module(nes)
ASSETS='Assets/snescn/common';SAVES='Saves/snescn/common'
LOADER_SHA='3effec579e2ed9de03f4150c0e35a4d1f189016e545e21139be6f0816e039fe9'

def headers(card,out):
    card=Path(card).resolve();out=Path(out).resolve()
    if out.exists() or out.is_relative_to(card):raise ValueError('Fresh output outside card required')
    ident=nes.identity(card);rows=[]
    for p in sorted((card/'Assets/snes/common/0.FAVORITES').rglob('*')):
        if not p.is_file() or p.suffix.lower() not in ['.sfc','.smc','.bin']:continue
        rel=p.relative_to(card).as_posix();nes.safe_path(card,rel)
        raw=p.read_bytes();offset=len(raw)&512
        chunks=[]
        for addr in [0x7fbd,0xffbd,0x40ffbd]:
            at=addr+offset
            if at<len(raw):chunks.append({'offset':at,'data':base64.b64encode(raw[at:at+128]).decode()})
        rows.append({'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'headers':chunks})
    if not rows:raise ValueError('No SNES favorites found')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({'identity':ident,'rows':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def decide(header_file,loader,simulator,out):
    """Use sparse header fixtures, never copy a user's complete ROM into the VM."""
    out=Path(out)
    if out.exists():raise ValueError('Fresh decision output required')
    loader=Path(loader).resolve()
    if nes.sha(loader)!=LOADER_SHA:raise ValueError('Upstream loader SHA mismatch')
    data=json.loads(Path(header_file).read_text(encoding='utf8'));rows=[]
    with tempfile.TemporaryDirectory(prefix='snes-headers-') as tmp:
        folder=Path(tmp);rom=folder/'rom.fixture'
        (folder/'save.fixture').write_bytes(bytes(131072))
        (folder/'data.json').write_text(json.dumps({'data':{'data_slots':[
            {'id':0,'filename':'rom.fixture'},{'id':10,'filename':'save.fixture'}]}}))
        for source in data['rows']:
            row={k:source[k] for k in ['path','bytes','sha256']}
            if source['bytes']<32768 or source['bytes']>16777216+512:
                row['error']='Unsupported ROM length';rows.append(row);continue
            with rom.open('wb') as f:
                f.truncate(source['bytes'])
                for chunk in source['headers']:
                    f.seek(chunk['offset']);f.write(base64.b64decode(chunk['data']))
            result=subprocess.run([str(simulator),'--bin',str(loader),'--data-json',str(folder/'data.json'),'--json'],capture_output=True,text=True,timeout=45)
            answer=json.loads(result.stdout);logs=answer.get('logs',[])
            writes={int(m[2],16):int(m[1],16) for line in logs
                if (m:=re.search(r'pmpw write (0x[\da-fA-F]+) to FPGA memory at (0x[\da-fA-F]+)$',line))}
            offsets=[int(m[1],16) for line in logs if (m:=re.search(r'Adjusting offset of file 0x0 to (0x[\da-fA-F]+)',line))]
            if result.returncode or answer.get('core') is None or not all(k in writes for k in [4,8,12,16]) or len(offsets)!=1:
                row['error']='Upstream loader refused header fixture'
            else:
                row.update(core=answer['core'],chip=writes[8],rom_size=writes[4],ram_size=writes[12],pal=writes[16],rom_offset=offsets[0])
            rows.append(row)
    receipt={'identity':data['identity'],'loader_sha256':LOADER_SHA,'rows':rows,
        'scope':'Actual upstream loader on same-size sparse header fixtures; FPGA/host operations are stubs, no game execution'}
    out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def build(card,decisions,out,titles=None,covers=None):
    card,out=Path(card).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(card) or card.is_relative_to(out):raise ValueError('Fresh staging outside card required')
    ident=nes.identity(card);metadata=json.loads(Path(decisions).read_text(encoding='utf8'))
    if ident!=metadata['identity'] or metadata['loader_sha256']!=LOADER_SHA:raise ValueError('Card/loader provenance mismatch')
    aliases={} if titles is None else json.loads(Path(titles).read_text(encoding='utf-8-sig'))
    if not isinstance(aliases,dict) or any(not isinstance(t,str) or not t.strip() for t in aliases.values()):raise ValueError('Nonempty title mapping required')
    covers=Path(covers).resolve() if covers else None
    if covers and not covers.is_dir():raise ValueError('Cover directory missing')
    groups={};excluded=[];sources=[];seen=set()
    for row in metadata['rows']:
        rel=row['path'];reason=None
        if any(re.match(r'^9[09][. _-]',p) for p in PurePosixPath(rel).parts):reason='alternate version folder retained in original library'
        elif 'error' in row:reason=row['error']
        elif row['core']!=0 or row['pal'] or row['chip'] not in [0,1,2]:reason='PAL or co-processor requires the original upstream core'
        elif row['ram_size']>7 or row['rom_size']>15 or row['rom_offset'] not in [0,512]:reason='unsupported cartridge metadata'
        p=nes.safe_path(card,rel)
        if p.stat().st_size!=row['bytes'] or nes.sha(p)!=row['sha256']:raise ValueError('ROM changed since header audit: '+rel)
        if row['sha256'] in seen:reason='duplicate bytes retained in original library'
        if reason:excluded.append({'path':rel,'reason':reason});continue
        seen.add(row['sha256']);tag=row['sha256'][:20]
        entry={'title':aliases.get(rel,p.stem),'folder':False,'rom':'/'+rel,'bytes':row['bytes']-row['rom_offset'],
            'rom_offset':row['rom_offset'],'rom_config':row['chip']|(row['rom_size']<<8)|(row['ram_size']<<12),
            'save_bytes':0 if row['ram_size']==0 else 1024<<row['ram_size'],
            'save':f'/{SAVES}/{tag}.sav','rtc':f'/{SAVES}/{tag}.rtc'}
        series=PurePosixPath(rel).parts[4] if len(PurePosixPath(rel).parts)>5 else '游戏'
        groups.setdefault(series,[]).append(entry);sources.append(row)
    if not sources:raise ValueError('No supported standard NTSC favorites')
    out.mkdir(parents=True);files=[]
    def write(rel,raw):
        p=nes.safe_path(out,rel);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        files.append({'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    def folder(path,title):return {'title':title,'folder':True,'rom':path,'save_bytes':0,'save':f'/{SAVES}/'+('0'*20)+'.sav','rtc':f'/{SAVES}/'+('0'*20)+'.rtc'}
    home=f'/{ASSETS}/menu.bin';root=[]
    for series,entries in groups.items():
        path=f'/{ASSETS}/libs/{hashlib.sha256(series.encode()).hexdigest()[:16]}.bin'
        write(path[1:],nes.pack(entries+[folder(home,'返回首页')],covers,'snes','snescn'))
        root.append(folder(path,aliases.get('folder:'+series,series)))
        for e in entries:
            if e['save_bytes']==0:continue
            rel=e['save'][1:];existing=nes.safe_path(card,rel)
            if existing.is_file():
                if existing.stat().st_size!=e['save_bytes']:raise ValueError('Unexpected existing preview save size: '+rel)
            else:write(rel,bytes(e['save_bytes']))
    write(home[1:],nes.pack(root+[folder(home,'返回首页')],covers,'snes','snescn'))
    result={'format':'GBAF1/SNES','identity':ident,'files':files,'source_refs':sources,'excluded':excluded,
        'unique_games':len(sources),'pages':len(groups)+1,'rom_copies':0,'source_writes':0,'save_imports':0,
        'scope':'Standard NTSC only; isolated progress; original OS Quit/save path, device save acceptance pending'}
    (out/'library-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['headers','decide','build'])
    for k in ['card','out','headers','loader','simulator','decisions','titles','covers']:p.add_argument('--'+k)
    a=p.parse_args()
    if a.mode=='headers':headers(a.card,a.out)
    elif a.mode=='decide':decide(a.headers,a.loader,a.simulator,a.out)
    else:print(json.dumps({k:v for k,v in build(a.card,a.decisions,a.out,a.titles,a.covers).items() if k in ['unique_games','pages','rom_copies']}))
