#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read GB/GBC ROMs from a card copy and build a local v9 menu. Never writes source."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import struct
import zlib
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
FONT_SHA = 'e66385c79a0b8b24a466f3129930e08a966a935b4bf3b28c6bb17a9df9bf791d'
ASSETS = 'Assets/gbclab/common'
SAVES = '/Saves/gbclab/common'
MAX_ENTRIES = 2047
spec = importlib.util.spec_from_file_location('pack_base', ROOT/'core/tools/make_cover_pack.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def contained(path, root):
    return path.resolve().is_relative_to(root.resolve())

def font():
    path = ROOT/'assets/fonts/unifont-18.0.01.hex.gz'
    if sha(path) != FONT_SHA:
        raise ValueError('Font checksum mismatch')
    return {int(code, 16): bytes.fromhex(bits) for code, bits in
            (line.split(':') for line in gzip.decompress(path.read_bytes()).decode('ascii').splitlines())}

def columns(title, glyphs):
    result, missing = [], set()
    clipped = False
    for c in title:
        if ord(c) not in glyphs:
            missing.add(c)
        bitmap = glyphs.get(ord(c), glyphs[ord('?')])
        width = len(bitmap) // 2
        if len(result) + width > 492:
            clipped = True
            break
        rows = [int.from_bytes(bitmap[y*width//8:(y+1)*width//8], 'big') for y in range(16)]
        result.extend(sum(((rows[y] >> (width-1-x)) & 1) << y for y in range(16)) for x in range(width))
    if clipped:
        result += [0, 0x1000, 0, 0x1000, 0, 0x1000, 0, 0]
    if not result:
        raise ValueError('Empty title')
    return len(result), struct.pack('<512H', *(result+[0]*(512-len(result)))), clipped, sorted(missing)

def path_bytes(value):
    parts = PurePosixPath(value).parts
    if not value.startswith('/') or '\\' in value or '..' in parts or '\0' in value or len(value.encode()) >= 256:
        raise ValueError(f'Invalid APF path: {value}')
    if len(parts) < 5 or parts[1] not in ('Assets', 'Saves') or parts[2] not in ('gb', 'gbc', 'gbclab') or parts[3] != 'common':
        raise ValueError(f'Undeclared APF platform path: {value}')
    return value.encode().ljust(256, b'\0')

def picture(path, folder=False):
    if path:
        with Image.open(path) as image:
            image = image.convert('RGB')
    else:
        image = Image.new('RGB', (256, 256), '#171d27')
        draw = ImageDraw.Draw(image)
        if folder:
            draw.rounded_rectangle((38,65,218,197),radius=10,fill='#b5a46a')
            draw.rounded_rectangle((38,49,117,90),radius=7,fill='#b5a46a')
        else:
            draw.rounded_rectangle((60,33,196,219),radius=10,outline='#8fa8be',width=4)
            draw.rectangle((80,55,176,135),fill='#354351')
            draw.line((91,182,165,182),fill='#b5a46a',width=5)
    raw = bytearray()
    for size in (128,80):
        thumb = base.fit(image,size)
        for r,g,b in thumb.get_flattened_data():
            raw.extend(struct.pack('<H', ((r>>3)<<11)|((g>>2)<<5)|(b>>3)))
    return bytes(raw)

def pack(entries, glyphs, log_id, warnings):
    if not 1 <= len(entries) <= MAX_ENTRIES:
        raise ValueError(f'A folder needs 1..{MAX_ENTRIES} entries (including Back): {log_id}')
    tables, art, paths = [], [], []
    for entry in entries:
        title = entry['title']
        width, text, clipped, missing = columns(title, glyphs)
        if clipped or missing:
            warnings.append({'title':title,'truncated':clipped,'missing_glyphs':missing})
        flags = int(entry.get('gb_only',False)) | (128 if entry.get('folder') else 0)
        table = bytearray(128)
        table[:40] = title.encode('ascii','replace')[:39].ljust(40,b'\0')
        struct.pack_into('<B3xIIH',table,40,flags,entry.get('size',0),entry['crc'],width)
        tables.append(table)
        art.append(picture(entry.get('cover'),entry.get('folder',False))+text+bytes(65536-45568-1024))
        for path in (entry['rom'],f'{SAVES}/{entry["save_id"]}.sav',f'{SAVES}/{entry["save_id"]}.sus'):
            paths.append(path_bytes(path))
    return (struct.pack('<4sHHHH4x',b'GBCV',9,len(entries),128,80)+base.index_block([e.get('sort_title',e['title']) for e in entries])+
            b''.join(tables+art+paths)+path_bytes(f'{SAVES}/meta/{log_id}.log')+path_bytes(f'{SAVES}/meta/{log_id}.cfg'))

def build(card, out, titles=None, covers=None, bios=None):
    card, out = Path(card).resolve(), Path(out).resolve()
    if out.exists() or contained(out,card) or contained(card,out):
        raise ValueError('Output must be a new folder outside the input card/copy')
    glyphs = font()
    titles = {} if titles is None else json.loads(Path(titles).read_text(encoding='utf-8-sig'))
    if not isinstance(titles,dict) or any(not isinstance(v,str) or not v.strip() for v in titles.values()):
        raise ValueError('Titles must map relative ROM paths to nonempty display names')
    covers = Path(covers).resolve() if covers else None
    if covers and not covers.is_dir():
        raise ValueError('Covers directory does not exist')
    nodes = {'': {'title':'游戏库','children':set(),'games':[]}}
    inventory = []
    warnings = []
    def add_node(key, title):
        if key in nodes:
            return
        parent = key.rsplit('/',1)[0] if '/' in key else ''
        add_node(parent, PurePosixPath(parent).name)
        nodes[key] = {'title':title,'children':set(),'games':[]}
        nodes[parent]['children'].add(key)
    for platform in ('gb','gbc'):
        base_dir = card/f'Assets/{platform}/common'
        if not base_dir.exists():
            continue
        if not contained(base_dir,card):
            raise ValueError('Input platform resolves outside card')
        for file in sorted(base_dir.rglob('*')):
            if file.suffix.lower() not in ('.gb','.gbc') or not file.is_file():
                continue
            if not contained(file,card) or file.is_symlink():
                raise ValueError('ROM link resolves outside card or is a symbolic link')
            relative = file.relative_to(card).as_posix()
            path_bytes('/'+relative)
            raw = file.read_bytes()
            if not 0x150 <= len(raw) <= 8*1024*1024:
                raise ValueError(f'Unsupported ROM size: {relative}')
            digest = hashlib.sha256(raw).hexdigest()
            key = platform+'/'+file.relative_to(base_dir).parent.as_posix()
            key = key.removesuffix('/.')
            for n in range(1,len(PurePosixPath(key).parts)+1):
                sub = '/'.join(PurePosixPath(key).parts[:n])
                add_node(sub,sub.upper()+' 游戏库' if sub in ('gb','gbc') else PurePosixPath(sub).name)
            cover = covers/Path(relative).with_suffix('.png') if covers else None
            if cover and (not cover.is_file()): cover=None
            if cover and not contained(cover,covers): raise ValueError('Cover resolves outside cover root')
            entry = {'title':titles.get(relative,file.stem),'rom':'/'+relative,'size':len(raw),'crc':zlib.crc32(raw),
                     'gb_only':raw[0x143] not in (0x80,0xC0),'save_id':digest[:20],'cover':cover}
            nodes[key]['games'].append(entry)
            inventory.append({'path':relative,'sha256':digest,'bytes':len(raw),'save':f'{SAVES}/{digest[:20]}.sav'})
    if not inventory:
        raise ValueError('No GB/GBC ROMs under Assets/gb/common or Assets/gbc/common')
    unknown = set(titles)-{i['path'] for i in inventory}
    if unknown:
        raise ValueError(f'Title mapping references missing ROMs: {sorted(unknown)}')
    def node_id(key): return 'root' if not key else hashlib.sha256(key.encode()).hexdigest()[:16]
    def node_path(key): return f'/{ASSETS}/'+('covers.bin' if not key else f'libs/{node_id(key)}.bin')
    def folder(key, title=None):
        return {'title':title or nodes[key]['title'],'rom':node_path(key),'crc':zlib.crc32(key.encode()),'folder':True,'save_id':'folders/'+node_id(key)}
    outputs = {}
    # Validate and render before creating any output or copying a BIOS.
    for key,node in sorted(nodes.items()):
        entries = [folder(child) for child in sorted(node['children'])]+node['games']
        entries.sort(key=lambda e:(base.letter_group(e['title']),e['title'].casefold(),e['rom']))
        # Native B navigation always opens entry count-1. Root must also have
        # a self-link; placing Back in the alphabetic order breaks B navigation.
        parent = key.rsplit('/',1)[0] if '/' in key else ''
        back = folder(parent,'返回上级' if key else '返回首页')
        back['sort_title'] = 'ZZZZZZZZ'
        entries.append(back)
        outputs[node_path(key).lstrip('/')] = pack(entries,glyphs,node_id(key),warnings)
    bios = Path(bios).resolve() if bios else None
    if bios and (not bios.is_file() or bios.stat().st_size!=2304):
        raise ValueError('GBC BIOS must be exactly 2304 bytes; size alone does not establish authenticity')
    needed = sum(map(len,outputs.values())) + (2304 if bios else 0)
    ancestor=out.parent
    while not ancestor.exists(): ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free < needed+1024*1024:
        raise ValueError('Not enough free space for staging')
    out.mkdir(parents=True)
    for rel,raw in outputs.items():
        file=out/rel;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(raw)
    if bios: shutil.copy2(bios,out/ASSETS/'gbc_bios.bin')
    for rel in ('','meta','folders'): (out/SAVES.lstrip('/')/rel).mkdir(parents=True,exist_ok=True)
    receipt={'format':9,'rom_count':len(inventory),'pack_count':len(outputs),'rom_copies':0,'source_writes':0,
             'source_refs':inventory,'warnings':warnings,'bios_included':bool(bios),
             'files':[{'path':p.relative_to(out).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file()]}
    (out/'library-manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return receipt

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--card',required=True,help='Read-only card root or local copy')
    p.add_argument('--out',required=True,help='New local staging directory, outside card')
    p.add_argument('--titles',help='UTF-8 JSON mapping relative ROM paths to display titles')
    p.add_argument('--covers',help='Optional PNG tree matching ROM paths relative to card')
    p.add_argument('--bios',help='Your own 2304-byte GBC BIOS (optional; required before play)')
    args=p.parse_args()
    try:
        result=build(args.card,args.out,args.titles,args.covers,args.bios)
    except (OSError,ValueError) as error:
        p.exit(2,str(error)+'\n')
    print(json.dumps({k:result[k] for k in ('rom_count','pack_count','rom_copies','source_writes','bios_included')},ensure_ascii=False))
    if result['warnings']: print('Title warnings: see library-manifest.json')

if __name__=='__main__': main()
