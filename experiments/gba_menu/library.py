#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a native 240x160 GBA menu locally. Original ROMs and progress are read-only."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import struct
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import build_library as gb
from menu_icons import LABELS, icon_image, kind

PLATFORM='gbalab'
ASSETS=f'Assets/{PLATFORM}/common'
SAVES=f'Saves/{PLATFORM}/common'
FRAME_BYTES=240*160*2
RECORD_BYTES=1024
MAX_ENTRIES=2047


def path_field(value):
    parts=PurePosixPath(value).parts
    if not value.startswith('/') or '\\' in value or '\0' in value or ':' in value or '..' in parts or len(value.encode())>=256:
        raise ValueError('Unsafe or oversized APF path')
    if not any(value.startswith('/'+p+'/') for p in (ASSETS,SAVES,'Assets/gba/common')):
        raise ValueError('Path outside GBA menu namespaces')
    return value.encode().ljust(256,b'\0')


def text(image,value,y,color='#e8e6dd',center=True):
    glyphs=gb.font()
    width,raw,clipped,missing=gb.columns(value,glyphs)
    if missing:raise ValueError('Unavailable title characters: '+''.join(missing))
    if width>232:raise ValueError('Display line exceeds 232 pixels')
    x=(240-width)//2 if center else 4
    draw=ImageDraw.Draw(image)
    columns=struct.unpack('<512H',raw)
    for col in range(width):
        for row in range(16):
            if columns[col]&(1<<row):draw.point((x+col,y+row),fill=color)


def title_lines(title):
    lines=['']
    for c in title.strip():
        candidate=lines[-1]+c
        if gb.columns(candidate,gb.font())[0]>224:
            if len(lines)==2:
                lines[-1]=lines[-1][:-2]+'…'
                break
            lines.append(c)
        else:lines[-1]=candidate
    return lines


def art(entry,covers=None):
    if entry['folder']:
        return icon_image(kind(entry['title']))
    if covers:
        p=covers/Path(entry['rom'].lstrip('/')).with_suffix('.png')
        if p.is_file():
            if not p.resolve().is_relative_to(covers):raise ValueError('Cover escapes root')
            with Image.open(p) as source:return source.convert('RGB')
    # Original cartridge illustration when the user's cover is unavailable.
    image=Image.new('RGB',(128,128),'black');d=ImageDraw.Draw(image)
    d.rounded_rectangle((25,24,103,105),radius=7,fill='#6663a6')
    d.rectangle((37,31,91,37),fill='#242b36')
    d.rectangle((34,44,94,92),fill='#d2cba9')
    d.polygon(((52,78),(70,51),(82,78)),fill='#718d84')
    d.rectangle((45,95,83,101),fill='#242b36')
    return image


def frame(entries,index,covers=None):
    image=Image.new('RGB',(240,160),'black')
    for position,size,brightness,entry in (
        ((2,35),48,.42,entries[(index-1)%len(entries)]),
        ((72,5),96,1.0,entries[index]),
        ((190,35),48,.42,entries[(index+1)%len(entries)])):
        cover=ImageOps.contain(art(entry,covers),(size,size),Image.Resampling.LANCZOS)
        cover=ImageEnhance.Brightness(cover).enhance(brightness)
        image.paste(cover,(position[0]+(size-cover.width)//2,position[1]+(size-cover.height)//2))
    for line,y in zip(title_lines(entries[index]['title']),(108,125)):
        text(image,line,y)
    text(image,'A 选择   B 返回',144,color='#abb1bc')
    return image


def pause_frame(selected):
    image=Image.new('RGB',(240,160),'black')
    text(image,'游戏已暂停',30)
    text(image,'继续游戏',70,color='#d2ab55' if selected==0 else '#abb1bc')
    text(image,'保存并返回',98,color='#d2ab55' if selected==1 else '#abb1bc')
    text(image,'A 确认   B 继续',140,color='#abb1bc')
    return image


def rgb565(image):
    raw=bytearray()
    for r,g,b in image.get_flattened_data():raw.extend(struct.pack('<H',((r>>3)<<11)|((g>>2)<<5)|(b>>3)))
    return bytes(raw)


def pack(entries,covers=None):
    if not 1<=len(entries)<=MAX_ENTRIES or not entries[-1]['folder']:
        raise ValueError('Every page must have 1..2047 entries, including final parent')
    frame_base=64+len(entries)*RECORD_BYTES
    pause_base=frame_base+len(entries)*FRAME_BYTES
    header=struct.pack('<4s5I',b'GBAF',1,len(entries),frame_base,pause_base,0).ljust(64,b'\0')
    records=[]
    for entry in entries:
        record=struct.pack('<4s3I',b'ENT1',int(entry['folder']),entry.get('bytes',0),0).ljust(32,b'\0')
        save=f'/{SAVES}/{entry["id"]}.sav'
        rtc=f'/{SAVES}/{entry["id"]}.rtc'
        records.append((record+b''.join(path_field(p) for p in (entry['rom'],save,rtc))).ljust(RECORD_BYTES,b'\0'))
    return header+b''.join(records)+b''.join(rgb565(frame(entries,i,covers)) for i in range(len(entries)))+b''.join(rgb565(pause_frame(i)) for i in range(2))


def build(card,out,titles=None,covers=None,folder_titles=None,skip_invalid=False):
    card,out=Path(card).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(card) or card.is_relative_to(out):
        raise ValueError('Use a new local output outside the input card/copy')
    titles={} if not titles else json.loads(Path(titles).read_text(encoding='utf-8-sig'))
    if not isinstance(titles,dict) or any(not isinstance(t,str) or not t.strip() for t in titles.values()):
        raise ValueError('Titles must map card-relative paths to nonempty display titles')
    folder_titles={} if not folder_titles else json.loads(Path(folder_titles).read_text(encoding='utf-8-sig'))
    if not isinstance(folder_titles,dict) or any(not isinstance(t,str) or not t.strip() for t in folder_titles.values()):
        raise ValueError('Folder titles must map logical gba/... paths to nonempty titles')
    covers=Path(covers).resolve() if covers else None
    if covers and not covers.is_dir():raise ValueError('Cover directory missing')
    base=card/'Assets/gba/common'
    if not base.is_dir() or not base.resolve().is_relative_to(card):raise ValueError('Missing GBA directory')
    nodes={'':{'title':'游戏大本营','parent':'','children':set(),'games':[]}}
    inventory=[];ids={};skipped=[];source_paths=set()
    def ensure(key):
        if key in nodes:return
        parent=key.rsplit('/',1)[0] if '/' in key else ''
        ensure(parent)
        leaf=key.rsplit('/',1)[-1]
        nodes[key]={'title':folder_titles.get(key,'GBA 游戏库' if key=='gba' else LABELS.get(leaf,leaf)),'parent':parent,'children':set(),'games':[]}
        nodes[parent]['children'].add(key)
    for file in sorted(base.rglob('*')):
        if not file.is_file() or file.suffix.lower()!='.gba':continue
        if file.is_symlink() or not file.resolve().is_relative_to(base):raise ValueError('ROM link escapes input')
        rel=file.relative_to(card).as_posix();path_field('/'+rel);source_paths.add(rel)
        raw=file.read_bytes()
        if not 192<=len(raw)<=32*1024**2 or len(raw)%4 or raw[0xB2]!=0x96 or (-sum(raw[0xA0:0xBD])-0x19)&255!=raw[0xBD]:
            if skip_invalid:
                skipped.append({'path':rel,'reason':'GBA size/fixed header byte/complement check failed'});continue
            raise ValueError('GBA size/header check failed: '+rel)
        digest=hashlib.sha256(raw).hexdigest();id_=digest[:20]
        if id_ in ids and ids[id_]!=digest:raise ValueError('Truncated ROM identity collision')
        ids[id_]=digest
        key='gba/'+file.relative_to(base).parent.as_posix();key=key.removesuffix('/.')
        ensure(key)
        nodes[key]['games'].append({'title':titles.get(rel,file.stem),'rom':'/'+rel,'id':id_,'bytes':len(raw),'folder':False})
        inventory.append({'path':rel,'sha256':digest,'bytes':len(raw),'save_bytes':131072 if b'FLASH1M_V' in raw else 65536,
                          'save':f'{SAVES}/{id_}.sav','rtc':f'{SAVES}/{id_}.rtc'})
    if not inventory:raise ValueError('No GBA ROMs found')
    if set(titles)-source_paths:raise ValueError('Unknown title mapping path')
    def page_id(key):return 'root' if not key else hashlib.sha256(key.encode()).hexdigest()[:16]
    def page_path(key):return f'/{ASSETS}/'+('menu.bin' if not key else 'libs/'+page_id(key)+'.bin')
    def folder(key,title=None):
        return {'title':title or nodes[key]['title'],'rom':page_path(key),'id':hashlib.sha256(('folder/'+key).encode()).hexdigest()[:20],'folder':True}
    # Validate names/paths before writing any output, and estimate total page size.
    pages={}
    for key,node in sorted(nodes.items()):
        entries=[folder(k) for k in sorted(node['children'])]+sorted(node['games'],key=lambda e:e['title'].casefold())
        entries.append(folder(node['parent'],'返回上级' if key else '返回首页'))
        if len(entries)>MAX_ENTRIES:raise ValueError('Page exceeds 2047 entries: '+key)
        for entry in entries:title_lines(entry['title']);path_field(entry['rom'])
        pages[page_path(key).lstrip('/')]=entries
    needed=sum(64+len(e)*1024+(len(e)+2)*FRAME_BYTES for e in pages.values())
    ancestor=out.parent
    while not ancestor.exists():ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free<needed+1024**2:raise ValueError('Insufficient output space')
    out.mkdir(parents=True)
    files=[]
    for rel,entries in pages.items():
        path=out/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(pack(entries,covers))
        files.append({'path':rel,'sha256':gb.sha(path),'bytes':path.stat().st_size})
    receipt={'format':'GBAF1','source_writes':0,'rom_copies':0,'save_writes':0,'roms':inventory,'files':files,'skipped':skipped,
             'hardware_playtest':'pending','note':'GBA ordinary saves and RTC only; APF sleep/memories disabled in experimental core'}
    (out/'library-manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--card',required=True);p.add_argument('--out',required=True)
    p.add_argument('--titles');p.add_argument('--covers');p.add_argument('--folders')
    p.add_argument('--skip-invalid',action='store_true',help='Exclude invalid headers and record every exclusion; never patch ROMs')
    a=p.parse_args()
    try:
        r=build(a.card,a.out,a.titles,a.covers,a.folders,a.skip_invalid)
        print(json.dumps({'roms':len(r['roms']),'pages':len(r['files']),'skipped':len(r['skipped']),'source_writes':0,'save_writes':0}))
    except (OSError,ValueError) as error:p.exit(2,str(error)+'\n')
