#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage GBA artwork/footer updates while preserving every launch/save record."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from PIL import Image,ImageEnhance,ImageOps
from library import ASSETS,FRAME_BYTES,RECORD_BYTES,MAX_ENTRIES,path_field,rgb565,text,title_lines

def sha(raw):return hashlib.sha256(raw).hexdigest()

def unpack(raw):
    if len(raw)<64:raise ValueError('Truncated GBA page')
    magic,version,count,base,pause,reserved=struct.unpack_from('<4s5I',raw)
    if (magic!=b'GBAF' or version!=1 or not 1<=count<=MAX_ENTRIES or reserved or
        base!=64+count*RECORD_BYTES or pause!=base+count*FRAME_BYTES or len(raw)!=pause+2*FRAME_BYTES):
        raise ValueError('Invalid GBA page layout')
    entries=[]
    for i in range(count):
        row=raw[64+i*RECORD_BYTES:64+(i+1)*RECORD_BYTES]
        tag,folder=struct.unpack_from('<4sI',row)
        if tag!=b'ENT1' or folder not in (0,1):raise ValueError('Invalid GBA entry')
        fields=[]
        for at in (32,288,544):
            value=row[at:at+256].split(b'\0',1)[0].decode('utf8');path_field(value);fields.append(value)
        entries.append({'folder':bool(folder),'rom':fields[0]})
    if not entries[-1]['folder']:raise ValueError('Missing parent entry')
    return entries,base,pause

def image(raw):return Image.frombytes('RGB',(240,160),raw,'raw','BGR;16')

def stage(card,out,covers=None,titles=None):
    card,out=Path(card).resolve(),Path(out).resolve()
    if out.exists() or out.is_relative_to(card) or card.is_relative_to(out):raise ValueError('Use fresh local output outside card')
    covers=Path(covers).resolve() if covers else None
    if covers and not covers.is_dir():raise ValueError('Missing covers')
    titles={} if not titles else json.loads(Path(titles).read_text(encoding='utf-8-sig'))
    if not isinstance(titles,dict):raise ValueError('Titles must be a path-to-caption mapping')
    titles={k.lstrip('/'):v for k,v in titles.items()}
    for key,value in titles.items():
        path_field('/'+key)
        if not isinstance(value,str) or not value.strip():raise ValueError('Empty caption')
        for line in title_lines(value):text(Image.new('RGB',(240,160)),line,0)
    root=card/ASSETS;paths=[root/'menu.bin',*sorted((root/'libs').glob('*.bin'))]
    pages=[]
    for p in paths:
        if p.is_symlink() or not p.resolve().is_relative_to(card):raise ValueError('Page escapes card')
        raw=p.read_bytes();entries,base,pause=unpack(raw);pages.append((p,raw,entries,base,pause))
    known={e['rom'].lstrip('/') for _,_,entries,_,_ in pages for e in entries}
    if set(titles)-known:raise ValueError('Unknown caption target')
    out.mkdir(parents=True);files=[];matched=0;caption_count=0
    for p,raw,entries,base,pause in pages:
        frames=[image(raw[base+i*FRAME_BYTES:base+(i+1)*FRAME_BYTES]) for i in range(len(entries))]
        arts=[];page_matches=0
        for i,entry in enumerate(entries):
            cover=covers/Path(entry['rom'].lstrip('/')).with_suffix('.png') if covers and not entry['folder'] else None
            if cover and cover.is_file():
                if not cover.resolve().is_relative_to(covers):raise ValueError('Cover escapes root')
                with Image.open(cover) as src:
                    if max(src.size)>4096:raise ValueError('Oversized cover')
                    arts.append(src.convert('RGB'))
                page_matches+=1
            else:arts.append(frames[i].crop((72,5,168,101)))
        result=bytearray(raw)
        for i,frame in enumerate(frames):
            if page_matches:
                frame.paste((0,0,0),(0,0,240,106))
                for pos,size,brightness,j in [((2,35),48,.42,(i-1)%len(entries)),((72,5),96,1,i),((190,35),48,.42,(i+1)%len(entries))]:
                    art=ImageOps.contain(arts[j],(size,size),Image.Resampling.LANCZOS)
                    art=ImageEnhance.Brightness(art).enhance(brightness)
                    frame.paste(art,(pos[0]+(size-art.width)//2,pos[1]+(size-art.height)//2))
            frame.paste((0,0,0),(0,144,240,160))
            title=titles.get(entries[i]['rom'].lstrip('/'))
            if titles and i==len(entries)-1:title='返回首页' if p.name=='menu.bin' else '返回上级'
            if title:
                frame.paste((0,0,0),(0,106,240,144))
                for line,y in zip(title_lines(title),(108,125)):text(frame,line,y)
                caption_count+=1
            start=base+i*FRAME_BYTES;result[start:start+FRAME_BYTES]=rgb565(frame)
            if not title and result[start+106*480:start+144*480]!=raw[start+106*480:start+144*480]:raise ValueError('Caption changed')
        for i in range(2):
            start=pause+i*FRAME_BYTES
            result[start+140*480:start+FRAME_BYTES]=bytes(20*480)
        if result[:base]!=raw[:base] or len(result)!=len(raw):raise ValueError('Launch/save records changed')
        rel=p.relative_to(card).as_posix();target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(result)
        files.append({'path':rel,'previous_sha256':sha(raw),'sha256':sha(result),'bytes':len(result),'matched_covers':page_matches})
        matched+=page_matches
    receipt={'format':'GBAF1','source_writes':0,'save_writes':0,'core_binary_writes':0,'records_preserved':True,'captions_preserved':not bool(titles),'captions_updated':caption_count,'matched_covers':matched,'files':files}
    (out/'display-update.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('card','out'):p.add_argument('--'+name,required=True)
    p.add_argument('--covers');p.add_argument('--titles');a=p.parse_args()
    try:
        r=stage(a.card,a.out,a.covers,a.titles);print(json.dumps({'pages':len(r['files']),'matched_covers':r['matched_covers'],'captions_updated':r['captions_updated'],'source_writes':0,'records_preserved':True}))
    except (OSError,ValueError) as error:p.exit(2,str(error)+'\n')
