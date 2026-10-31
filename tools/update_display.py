#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage GB/GBC title and cover updates while retaining ROM/save identities."""
import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import shutil
import struct

from PIL import Image,ImageDraw
import build_library as lib
from install import confined,identity
from style_library import ROOT_PACK,decode,encode


def title_card(title,platform):
    image=Image.new('RGB',(256,256),'black');draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((15,10,240,245),radius=12,outline='#718d84',width=3)
    lines=[platform.upper(),'文字封面','']
    for char in title:
        if lib.columns(lines[-1]+char,lib.font())[0]>200:
            if len(lines)==8:
                lines[-1]=lines[-1][:-2]+'…';break
            lines.append(char)
        else:lines[-1]+=char
    for i,line in enumerate(lines):
        if not line:continue
        width,raw,_,missing=lib.columns(line,lib.font())
        if missing:raise ValueError('Unavailable cover glyphs: '+''.join(missing))
        columns=struct.unpack('<512H',raw)
        for x in range(width):
            for y in range(16):
                if columns[x]&(1<<y):draw.point(((256-width)//2+x,24+i*27+y),fill='#e8e6dd')
    raw=bytearray()
    for size in (128,80):
        for r,g,b in lib.base.fit(image,size).get_flattened_data():
            raw.extend(struct.pack('<H',((r>>3)<<11)|((g>>2)<<5)|(b>>3)))
    return bytes(raw)


@lru_cache(maxsize=512)
def checked_picture(filename,digest):
    path=Path(filename)
    if lib.sha(path)!=digest:raise ValueError('Cover checksum mismatch: '+filename)
    return lib.picture(path)


def stage(card,out,mapping):
    card,out=Path(card).resolve(),Path(out).resolve()
    if out.exists() or lib.contained(out,card) or lib.contained(card,out):
        raise ValueError('Use a new local staging directory outside the card')
    ident=identity(card);out.mkdir(parents=True)
    pending=[ROOT_PACK];seen=set();sources=[];outputs=[];changed_games=set();refs=set();warnings=[]
    for path in mapping:
        if not path.startswith(('/Assets/gb/common/','/Assets/gbc/common/')):raise ValueError('Unexpected game path')
        lib.path_bytes(path)
    while pending:
        rel=pending.pop()
        if rel in seen:continue
        seen.add(rel);source=confined(card,rel);original=source.read_bytes();pack=decode(original)
        sources.append({'path':rel,'sha256':hashlib.sha256(original).hexdigest()})
        titles={}
        for entry in pack['entries']:
            rom=entry['paths'][0]
            if entry['record'][40]&128:
                pending.append(rom.lstrip('/'));continue
            refs.add(rom);patch=mapping.get(rom,{})
            title=patch.get('title',entry['record'][:40].split(b'\0')[0].decode('ascii'))
            titles[rom]=title;before=entry['record'],entry['blob']
            if 'title' in patch:
                width,text,clipped,missing=lib.columns(title,lib.font())
                if missing:raise ValueError('Unavailable title glyphs: '+''.join(missing))
                if clipped:warnings.append({'rom':rom,'title':title,'truncated':True})
                record=bytearray(entry['record']);record[:40]=title.encode('ascii','replace')[:39].ljust(40,b'\0')
                struct.pack_into('<H',record,52,width);entry['record']=bytes(record)
                entry['blob']=entry['blob'][:45568]+text+entry['blob'][46592:]
            art=checked_picture(patch['cover'],patch['cover_sha256']) if patch.get('cover') else title_card(title,rom.split('/')[2]) if patch.get('fallback') else None
            if art:entry['blob']=art+entry['blob'][45568:]
            if before!=(entry['record'],entry['blob']):changed_games.add(rom)
        if titles and all(not e['record'][40]&128 for e in pack['entries'][:-1]):
            if set(titles)-set(mapping):raise ValueError('Sorting requires a display title for every game in the page')
            if b'FPR1' in pack['header'] or b'FPR2' in pack['header']:raise ValueError('Cartridge fingerprint indexes need remapping before sorting')
            games=sorted(pack['entries'][:-1],key=lambda e:(not bool(e['record'][40]&2),lib.base.letter_group(titles[e['paths'][0]]),titles[e['paths'][0]].casefold(),e['paths'][0]))
            pack['entries']=games+[pack['entries'][-1]]
            index=lib.base.index_block([titles[e['paths'][0]] for e in games]+['ZZZZZZZZ'],fav_count=sum(bool(e['record'][40]&2) for e in games))
            header=bytearray(pack['header']);header[16:80]=index[:64];pack['header']=bytes(header)
        raw=encode(pack);decode(raw)
        if raw!=original:
            target=confined(out,rel);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            outputs.append({'path':rel,'bytes':len(raw),'sha256':lib.sha(target)})
    bios_rel=lib.ASSETS+'/gbc_bios.bin';bios=confined(card,bios_rel)
    target=confined(out,bios_rel);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(bios,target)
    outputs.append({'path':bios_rel,'bytes':target.stat().st_size,'sha256':lib.sha(target)})
    # Installer expects Home even when only child pages have changed.
    if ROOT_PACK not in {x['path'] for x in outputs}:
        target=confined(out,ROOT_PACK);shutil.copy2(confined(card,ROOT_PACK),target)
        outputs.append({'path':ROOT_PACK,'bytes':target.stat().st_size,'sha256':lib.sha(target)})
    result={'format':9,'identity':ident,'source_packs':sources,'source_refs':[],'files':outputs,
            'unique_games':len(refs),'updated_games':len(changed_games),'reachable_pages':len(seen),
            'unmatched_mapping':sorted(set(mapping)-refs),'warnings':warnings,'rom_copies':0,'save_writes':0,'source_writes':0}
    (out/'library-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('card','out','mapping'):p.add_argument('--'+flag,required=True)
    a=p.parse_args()
    try:
        result=stage(a.card,a.out,json.loads(Path(a.mapping).read_text(encoding='utf8')))
        print(json.dumps({k:result[k] for k in ('unique_games','updated_games','reachable_pages','unmatched_mapping')}))
    except (OSError,ValueError) as e:p.exit(2,str(e)+'\n')
