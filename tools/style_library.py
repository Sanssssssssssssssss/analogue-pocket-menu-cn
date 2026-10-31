#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage machine icons over an existing v9 GB/GBC library, retaining game/save paths."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zlib

import build_library as lib
from install import confined, identity
from menu_icons import LABELS, cover_bytes, kind

ROOT_PACK = lib.ASSETS + '/covers.bin'
CLASSICS_ID = hashlib.sha256(b'machine-menu/classics/v1').hexdigest()[:16]
CLASSICS_PACK = lib.ASSETS + '/libs/' + CLASSICS_ID + '.bin'


def decode(raw):
    if len(raw) < 1040:
        raise ValueError('Truncated menu pack')
    magic, version, count, cw, tw = struct.unpack_from('<4sHHHH', raw)
    if (magic, version, cw, tw) != (b'GBCV', 9, 128, 80) or not 1 <= count <= lib.MAX_ENTRIES:
        raise ValueError('Only v9 128/80 pixel menu packs are supported')
    if len(raw) != 1040 + count * (128 + 65536 + 768):
        raise ValueError('Truncated or extended menu pack')
    art0, paths0 = 528 + count*128, 528 + count*(128+65536)
    entries = []
    for i in range(count):
        paths = []
        for j in range(3):
            field = raw[paths0 + (i*3+j)*256:paths0 + (i*3+j+1)*256]
            value = field.split(b'\0')[0].decode('utf-8')
            if field != lib.path_bytes(value):
                raise ValueError('Noncanonical pack path')
            paths.append(value)
        record = raw[528+i*128:528+(i+1)*128]
        if record[40] & 128 and not paths[0].startswith('/'+lib.ASSETS+'/'):
            raise ValueError('Folder link escapes the menu asset tree')
        if not record[40] & 128 and not paths[0].startswith(('/Assets/gb/common/', '/Assets/gbc/common/')):
            raise ValueError('Game link escapes GB/GBC asset trees')
        if not paths[1].startswith(lib.SAVES+'/') or not paths[2].startswith(lib.SAVES+'/'):
            raise ValueError('Save link escapes the experimental save tree')
        entries.append({'record': record, 'blob': raw[art0+i*65536:art0+(i+1)*65536], 'paths': paths})
    if not entries[-1]['record'][40] & 128:
        raise ValueError('Final parent entry must be a folder')
    return {'header':raw[:528], 'entries':entries, 'tail':raw[-512:]}


def encode(pack):
    entries = pack['entries']
    header = bytearray(pack['header'])
    struct.pack_into('<H', header, 6, len(entries))
    return bytes(header) + b''.join(e['record'] for e in entries) + b''.join(e['blob'] for e in entries) + b''.join(
        lib.path_bytes(p) for e in entries for p in e['paths']) + pack['tail']


def restyle(entry, icon, title=None):
    result = {**entry, 'paths':list(entry['paths'])}
    result['blob'] = cover_bytes(icon) + entry['blob'][45568:]
    if title:
        width, text, clipped, missing = lib.columns(title, lib.font())
        if clipped or missing:
            raise ValueError('Menu label cannot be rendered')
        record = bytearray(entry['record'])
        record[:40] = title.encode('ascii','replace')[:39].ljust(40,b'\0')
        struct.pack_into('<H', record, 52, width)
        result['record'] = bytes(record)
        result['blob'] = result['blob'][:45568] + text + result['blob'][46592:]
    return result


def display_label(entry):
    fallback = entry['record'][:40].split(b'\0')[0].decode('ascii')
    if '?' not in fallback:
        return LABELS.get(fallback, fallback)
    for title in set(LABELS.values()) | {'其他经典', '精选主入口', '系列备选版本'}:
        if lib.columns(title, lib.font())[1] == entry['blob'][45568:46592]:
            return title
    return None


def style(card, out):
    card, out = Path(card).resolve(), Path(out).resolve()
    if out.exists() or lib.contained(out, card) or lib.contained(card, out):
        raise ValueError('Use a fresh staging folder outside the card/copy')
    ident = identity(card)
    root_path = confined(card, ROOT_PACK)
    root = decode(root_path.read_bytes())
    if any(not e['record'][40] & 128 for e in root['entries']):
        raise ValueError('This layout requires a folder-only home page')
    if root['entries'][-1]['paths'][0] != '/'+ROOT_PACK:
        raise ValueError('Home parent must point to Home')
    platforms, classics = {}, []
    for entry in root['entries'][:-1]:
        fallback = entry['record'][:40].split(b'\0')[0].decode('ascii')
        platform = next((p for p in ('gb','gbc') if fallback.startswith(p.upper()+' ')), None)
        if platform:
            if platform in platforms:
                raise ValueError('Duplicate machine entry')
            platforms[platform] = entry
        else:
            classics.append(entry)
    if not platforms:
        raise ValueError('No GB or GBC machine entries found')
    if any(e['paths'][0] == '/'+CLASSICS_PACK for e in classics):
        raise ValueError('Library already has this machine layout; rebuild from the previous backup to restyle')
    source_packs, outputs = {ROOT_PACK:lib.sha(root_path)}, {}
    for platform, entry in platforms.items():
        rel = entry['paths'][0].lstrip('/')
        source = confined(card, rel)
        pack = decode(source.read_bytes())
        if pack['entries'][-1]['paths'][0] != '/'+ROOT_PACK:
            raise ValueError('Machine page must return to Home')
        source_packs[rel] = lib.sha(source)
        styled = []
        for i, child in enumerate(pack['entries']):
            if child['record'][40] & 128:
                title = display_label(child)
                linked = confined(card, child['paths'][0].lstrip('/'))
                if not linked.is_file():
                    raise ValueError('Missing menu link: '+child['paths'][0])
                if i == len(pack['entries'])-1:
                    child = restyle(child, 'back')
                elif title:
                    child = restyle(child, kind(title), title)
                else:
                    # Existing translated text is preserved; use a distinct, original folder icon.
                    child = restyle(child, 'folder')
            styled.append(child)
        pack['entries'] = styled
        outputs[rel] = encode(pack)
    home = []
    for platform in ('gb','gbc'):
        if platform in platforms:
            entry = restyle(platforms[platform], platform)
            record = bytearray(entry['record']); record[40] &= ~2
            entry['record'] = bytes(record)
            home.append(entry)
    if classics:
        target = confined(card, CLASSICS_PACK)
        if target.exists():
            raise ValueError('New classics pack would overwrite an existing file')
        machine_paths = {entry['paths'][0] for entry in platforms.values()}
        for entry in classics:
            if entry['paths'][0] in machine_paths:
                raise ValueError('A classic shortcut cannot also be a machine page')
            rel = entry['paths'][0].lstrip('/')
            source = confined(card, rel)
            pack = decode(source.read_bytes())
            if pack['entries'][-1]['paths'][0] != '/'+ROOT_PACK:
                raise ValueError('Classic page has an unexpected parent')
            source_packs[rel] = lib.sha(source)
            pack['entries'][-1]['paths'][0] = '/'+CLASSICS_PACK
            outputs[rel] = encode(pack)
        # The old classic entries retain their exact identities, art, save paths and order.
        classic_pack = {**root, 'entries':classics+[restyle(root['entries'][-1], 'back')]}
        classic_header = bytearray(root['header'])
        favourite_count = sum(bool(e['record'][40] & 2) for e in classics)
        if any(not e['record'][40] & 2 for e in classics[:favourite_count]):
            raise ValueError('Noncontiguous classic favourites')
        titles = [e['record'][:40].split(b'\0')[0].decode('ascii') for e in classics]+['ZZZZZZZZ']
        classic_header[16:528] = lib.base.index_block(titles,fav_count=favourite_count)
        classic_pack['header'] = bytes(classic_header)
        classic_pack['tail'] = b''.join(lib.path_bytes(f'{lib.SAVES}/meta/{CLASSICS_ID}.{ext}') for ext in ('log','cfg'))
        outputs[CLASSICS_PACK] = encode(classic_pack)
        entry = restyle(root['entries'][-1], 'favorites', '经典收藏')
        record = bytearray(entry['record']); record[40] &= ~2
        struct.pack_into('<I',record,48,zlib.crc32(b'machine-menu/classics/v1'))
        entry['record'] = bytes(record)
        entry['paths'] = ['/'+CLASSICS_PACK]+[f'{lib.SAVES}/folders/{CLASSICS_ID}.{ext}' for ext in ('sav','sus')]
        home.append(entry)
    root['entries'] = home+[restyle(root['entries'][-1], 'back')]
    header = bytearray(root['header'])
    # Home has an explicit machine order; one section avoids alphabet jumps into reordered rows.
    header[16:528] = lib.base.index_block(['#']*len(home)+['ZZZZZZZZ'])
    root['header'] = bytes(header)
    outputs[ROOT_PACK] = encode(root)
    for raw in outputs.values():
        decode(raw)
    bios = confined(card, lib.ASSETS+'/gbc_bios.bin')
    if not bios.is_file() or bios.stat().st_size != 2304:
        raise ValueError('Existing 2304-byte GBC BIOS required')
    outputs[lib.ASSETS+'/gbc_bios.bin'] = bios.read_bytes()
    ancestor = out.parent
    while not ancestor.exists(): ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < sum(map(len,outputs.values()))+1024**2:
        raise ValueError('Insufficient staging space')
    out.mkdir(parents=True)
    for rel, raw in outputs.items():
        target=confined(out, rel);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    receipt = {'format':9, 'layout':'machines-first', 'identity':ident,
               'source_packs':[{'path':p,'sha256':digest} for p,digest in source_packs.items()],
               'source_refs':[], 'rom_copies':0, 'source_writes':0, 'save_writes':0,
               'game_entries_changed':0, 'home_machines':list(platforms), 'classic_shortcuts':len(classics),
               'files':[{'path':p,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for p,raw in sorted(outputs.items())]}
    (out/'library-manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--card',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    try:
        result=style(args.card,args.out)
    except (OSError,ValueError,UnicodeError) as error:
        parser.exit(2,str(error)+'\n')
    print(json.dumps({k:result[k] for k in ('layout','home_machines','classic_shortcuts','game_entries_changed','source_writes')},ensure_ascii=False))


if __name__ == '__main__': main()
