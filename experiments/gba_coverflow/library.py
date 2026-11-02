#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Upgrade verified local GBAF1 menu assets to the shared CoverFlow atlas format.

Reads menu packs and their recorded ROM identities only. Never reads, copies or
writes ROM/save bytes. The card is rechecked separately before installation.
"""
import argparse,hashlib,importlib.util,json,shutil,struct,sys
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import build_library as gb
from menu_icons import LABELS,kind
spec=importlib.util.spec_from_file_location('gba_f1',ROOT/'experiments/gba_menu/library.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
STRIDE=65536
ART_BYTES=45568

def field(raw):
    value=raw.split(b'\0',1)[0].decode('utf8')
    old.path_field(value)
    return value

def read_page(path):
    raw=path.read_bytes()
    if len(raw)<64:raise ValueError('Truncated source menu')
    magic,version,count,base,pause,_=struct.unpack_from('<4s5I',raw)
    if magic!=b'GBAF' or version!=1 or not 1<=count<=2047 or base!=64+count*1024 or pause!=base+count*old.FRAME_BYTES or len(raw)!=pause+2*old.FRAME_BYTES:
        raise ValueError('Source is not an exact GBAF1 pack')
    records=[]
    for i in range(count):
        record=raw[64+i*1024:64+(i+1)*1024]
        magic,flags,size,_=struct.unpack_from('<4s3I',record)
        if magic!=b'ENT1' or flags not in (0,1):raise ValueError('Invalid source record')
        paths=[field(record[32+j*256:288+j*256]) for j in range(3)]
        records.append({'record':record,'folder':bool(flags),'rom':paths[0],'bytes':size,'save':paths[1],'rtc':paths[2]})
    if not records[-1]['folder']:raise ValueError('Final source entry is not Back')
    return records,raw[pause:]

def mapping(path):
    value=json.loads(Path(path).read_text(encoding='utf-8-sig')) if path else {}
    if not isinstance(value,dict) or any(not isinstance(v,str) or not v.strip() for v in value.values()):raise ValueError('Expected nonempty title mapping')
    return value

def upgrade(source,out,titles=None,folders=None,covers=None):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(source) or source.is_relative_to(out):raise ValueError('Fresh local destination outside source required')
    manifest=json.loads((source/'library-manifest.json').read_text(encoding='utf8'))
    if manifest.get('format')!='GBAF1':raise ValueError('Expected verified GBAF1 manifest')
    titles,folders=mapping(titles),mapping(folders)
    covers=[Path(p).resolve() for p in covers or []]
    if any(not p.is_dir() for p in covers):raise ValueError('Cover root missing')
    page_titles={'/Assets/gbalab/common/menu.bin':'游戏大本营'}
    keys={'','gba'}
    for rom in manifest['roms']:
        rel=PurePosixPath(rom['path']).relative_to('Assets/gba/common')
        key='gba' if str(rel.parent)=='.' else 'gba/'+rel.parent.as_posix()
        while key:
            keys.add(key);key=key.rsplit('/',1)[0] if '/' in key else ''
    for key in keys- {''}:
        name=hashlib.sha256(key.encode()).hexdigest()[:16]
        page_titles[f'/Assets/gbalab/common/libs/{name}.bin']=folders.get(key,'GBA 游戏库' if key=='gba' else LABELS.get(key.rsplit('/',1)[-1],key.rsplit('/',1)[-1]))
    extra_titles=manifest.get('page_titles',{})
    if not isinstance(extra_titles,dict) or any(not isinstance(v,str) or not v.strip() for v in extra_titles.values()):raise ValueError('Invalid generated page titles')
    declared_pages={'/'+item['path'] for item in manifest['files']}
    if set(extra_titles)-declared_pages:raise ValueError('Page title references an undeclared menu')
    page_titles.update(extra_titles)
    plans=[];needed=0
    for item in manifest['files']:
        rel=PurePosixPath(item['path']);path=source/rel
        if rel.is_absolute() or '..' in rel.parts or not str(rel).startswith('Assets/gbalab/common/') or path.is_symlink() or not path.resolve().is_relative_to(source):raise ValueError('Source pack escapes menu namespace')
        if gb.sha(path)!=item['sha256']:raise ValueError('Source menu changed: '+str(rel))
        entries,pause=read_page(path)
        if len(entries)>128:raise ValueError('GBA CoverFlow has 128 texture slots per page; split the source library before conversion')
        plans.append((rel,entries,pause));needed+=64+len(entries)*(1024+STRIDE)+len(pause)
    ancestor=out.parent
    while not ancestor.exists():ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free<needed+1024**2:raise ValueError('Insufficient output space')
    out.mkdir(parents=True);files=[];warnings=[];matched=0;missing=0
    for rel,entries,pause in plans:
        tables=[];blobs=[]
        for i,entry in enumerate(entries):
            if i==len(entries)-1:title='返回上级' if str(rel)!='Assets/gbalab/common/menu.bin' else '返回首页'
            elif entry['folder']:title=page_titles.get(entry['rom'])
            else:title=titles.get(entry['rom'].lstrip('/'),PurePosixPath(entry['rom']).stem)
            if not title:raise ValueError('Missing folder label: '+entry['rom'])
            width,text,clipped,unknown=gb.columns(title,gb.font())
            subwidth,sub,_,subunknown=gb.columns('任天堂 GBA',gb.font())
            if unknown or subunknown:raise ValueError('Missing glyphs: '+''.join(unknown+subunknown))
            if clipped:warnings.append({'path':entry['rom'],'reason':'long title clipped to 500 columns'})
            cover=None
            if not entry['folder']:
                for cover_root in covers or []:
                    candidate=cover_root/Path(entry['rom'].lstrip('/')).with_suffix('.png')
                    if candidate.is_file():
                        if not candidate.resolve().is_relative_to(cover_root):raise ValueError('Cover escapes root')
                        cover=candidate;break
                if cover:matched+=1
                else:missing+=1
            picture=gb.picture(cover,entry['folder'],kind(title))
            if len(picture)!=ART_BYTES:raise ValueError('Wrong shared CoverFlow image layout')
            table=bytearray(entry['record']);struct.pack_into('<II',table,16,width,subwidth)
            # ROM/save/RTC path structs and content identities remain byte exact.
            if table[32:]!=entry['record'][32:]:raise AssertionError('Source path identity changed')
            tables.append(bytes(table));blobs.append((picture+text+sub).ljust(STRIDE,b'\0'))
        base=64+len(entries)*1024;pause_at=base+len(entries)*STRIDE
        header=struct.pack('<4s5I',b'GBAF',2,len(entries),base,pause_at,STRIDE).ljust(64,b'\0')
        dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(header+b''.join(tables+blobs)+pause)
        files.append({'path':str(rel),'sha256':gb.sha(dest),'bytes':dest.stat().st_size})
    receipt={'format':'GBAF2','rendering':'shared accepted GB/GBC CoverFlow, 128/80 RGB565 atlas and Unicode bitmap rows',
        'source_manifest_sha256':gb.sha(source/'library-manifest.json'),'source_writes':0,'rom_copies':0,'save_writes':0,
        'roms':manifest['roms'],'files':files,'warnings':warnings,'skipped':manifest.get('skipped',[]),'covers':{'matched_entry_references':matched,'missing_entry_references':missing},
        'hardware_playtest':'pending','rom_identity_status':'inherited snapshot; final card hash verification required'}
    (out/'library-manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--out',required=True)
    p.add_argument('--titles');p.add_argument('--folders');p.add_argument('--covers',nargs='+');a=p.parse_args()
    r=upgrade(a.source,a.out,a.titles,a.folders,a.covers)
    print(json.dumps({'format':r['format'],'pages':len(r['files']),'roms':len(r['roms']),'warnings':len(r['warnings']),'covers':r['covers']},ensure_ascii=False))
