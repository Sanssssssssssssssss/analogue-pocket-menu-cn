#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage NES-only menu pages and isolated initial saves; never writes the source card."""
import argparse,hashlib,importlib.util,json,re,struct,sys
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from install import identity,safe_path
from build_library import sha
sys.path.insert(0,str(ROOT/'experiments/multi_system'))
from launch_plan import inspect_rom
spec=importlib.util.spec_from_file_location('gba_library',ROOT/'experiments/gba_menu/library.py')
visual=importlib.util.module_from_spec(spec);spec.loader.exec_module(visual)
ASSETS='Assets/neslab/common';SAVES='Saves/neslab/common'

def path_bytes(value,platform='nes',namespace='neslab'):
    if (platform,namespace) not in [('nes','neslab'),('snes','snescn')]:raise ValueError('Unknown menu profile')
    if not value.startswith('/') or len(value.encode('utf8'))>=256:raise ValueError('Invalid APF path length')
    parts=PurePosixPath(value).parts
    if '..' in parts or '\\' in value or ':' in value or '\0' in value:raise ValueError('Unsafe APF path')
    if not any(value.startswith('/'+p+'/') for p in [f'Assets/{namespace}/common',f'Saves/{namespace}/common',f'Assets/{platform}/common']):raise ValueError('Foreign APF namespace')
    return value.encode('utf8').ljust(256,b'\0')

def pack(entries,covers=None,platform='nes',namespace='neslab'):
    if not (1<=len(entries)<=2047 and entries[-1]['folder']):raise ValueError('Menu requires a final parent entry')
    count=len(entries);base=64+count*1024;pause=base+count*76800
    header=struct.pack('<4s5I',b'GBAF',1,count,base,pause,0).ljust(64,b'\0')
    records=[]
    for entry in entries:
        row=bytearray(1024)
        struct.pack_into('<4s7I',row,0,b'ENT1',int(entry['folder']),entry.get('bytes',0),entry.get('save_bytes',262144),entry.get('rom_offset',0),entry.get('rom_config',0),0,0)
        for offset,key in [(32,'rom'),(288,'save'),(544,'rtc')]:row[offset:offset+256]=path_bytes(entry[key],platform,namespace)
        records.append(bytes(row))
    frames=b''.join(visual.rgb565(visual.frame(entries,i,covers)) for i in range(count))
    return header+b''.join(records)+frames+b''.join(visual.rgb565(visual.pause_frame(i)) for i in range(2))

def build(card,out,titles=None,covers=None):
    card,out=Path(card).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(card) or card.is_relative_to(out):raise ValueError('Use a fresh staging folder outside the card')
    ident=identity(card);titles={} if titles is None else json.loads(Path(titles).read_text(encoding='utf-8-sig'))
    if not isinstance(titles,dict) or any(not isinstance(t,str) or not t.strip() for t in titles.values()):raise ValueError('Nonempty title mapping required')
    covers=Path(covers).resolve() if covers else None
    if covers and not covers.is_dir():raise ValueError('Cover directory missing')
    base=card/'Assets/nes/common/0.FAVORITES'
    if not base.is_dir():raise ValueError('Missing NES favorites')
    sources=[];excluded=[];games=[];seen=set()
    for p in sorted(base.rglob('*')):
        if not p.is_file() or p.suffix.lower()!='.nes':continue
        rel=p.relative_to(card).as_posix()
        if any(re.match(r'^9[09][. _-]',part) for part in p.relative_to(base).parts[:-1]):
            excluded.append({'path':rel,'reason':'alternate version folder retained in original library'});continue
        safe_path(card,rel);data=p.read_bytes()
        try:info=inspect_rom('nes',data)
        except ValueError as error:excluded.append({'path':rel,'reason':str(error)});continue
        digest=hashlib.sha256(data).hexdigest()
        if digest in seen:excluded.append({'path':rel,'reason':'duplicate bytes retained in original library'});continue
        seen.add(digest);tag=digest[:20]
        entry={'title':titles.get(rel,p.stem),'folder':False,'rom':'/'+rel,'bytes':len(data),
               'save':f'/{SAVES}/{tag}.sav','rtc':f'/{SAVES}/{tag}.rtc'}
        for key in ['rom','save','rtc']:path_bytes(entry[key])
        for line in visual.title_lines(entry['title']):visual.text(visual.Image.new('RGB',(240,160)),line,0)
        games.append(entry);sources.append({'path':rel,'bytes':len(data),'sha256':digest,'mapper':info['mapper']})
    if not games:raise ValueError('No supported NES favorites')
    # Small, independent category pages use the existing favorites series directories.
    groups={}
    for e in games:
        series=PurePosixPath(e['rom']).parts[5] if len(PurePosixPath(e['rom']).parts)>6 else '游戏'
        groups.setdefault(series,[]).append(e)
    out.mkdir(parents=True);files=[]
    def write(rel,raw):
        p=safe_path(out,rel);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        files.append({'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    def folder(path,title):return {'title':title,'folder':True,'rom':path,
        'save':f'/{SAVES}/'+('0'*20)+'.sav','rtc':f'/{SAVES}/'+('0'*20)+'.rtc'}
    home=f'/{ASSETS}/menu.bin';root=[]
    for key,items in groups.items():
        path=f'/{ASSETS}/libs/{hashlib.sha256(key.encode()).hexdigest()[:16]}.bin'
        label=titles.get('folder:'+key,key)
        write(path.lstrip('/'),pack(items+[folder(home,'返回首页')],covers))
        root.append(folder(path,label))
    write(home.lstrip('/'),pack(root+[folder(home,'返回首页')],covers))
    for e in games:
        # Initial progress is deliberately isolated. Existing preview saves are never overwritten.
        rel=e['save'].lstrip('/');existing=safe_path(card,rel)
        if existing.is_file():
            if existing.stat().st_size!=262144:raise ValueError('Unexpected existing preview save size: '+rel)
            continue
        write(rel,bytes(262144))
    result={'format':'GBAF1/NES','identity':ident,'files':files,'source_refs':sources,
            'unique_games':len(games),'pages':len(groups)+1,'excluded':excluded,
            'rom_copies':0,'source_writes':0,'save_imports':0,
            'save_policy':'New isolated zero-filled 256 KiB saves only; do not overwrite existing progress',
            'scope':'Source staging only; requires independently compiled and accepted NES core'}
    (out/'library-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['card','out']:p.add_argument('--'+name,required=True)
    p.add_argument('--titles');p.add_argument('--covers');a=p.parse_args()
    r=build(a.card,a.out,a.titles,a.covers)
    print(json.dumps({k:r[k] for k in ['unique_games','pages','rom_copies','source_writes']}))
