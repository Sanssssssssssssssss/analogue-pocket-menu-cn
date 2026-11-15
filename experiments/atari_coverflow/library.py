#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build Atari menu pages at existing ROM paths; never writes a source save."""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import struct
import sys
from pathlib import Path, PurePosixPath
_spec = importlib.util.spec_from_file_location('atari_library_prepare', Path(__file__).with_name('prepare.py'))
_prepare = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prepare)
ROOT, PROFILES, load = _prepare.ROOT, _prepare.PROFILES, _prepare.load

shared = load('atari_atlas', ROOT/'experiments/nes_coverflow/library.py')
NAMES = {'2600': '雅达利 2600', '7800': '雅达利 7800'}
EXTENSIONS = {'2600': {'.a26', '.bin'}, '7800': {'.a78', '.a26', '.bin'}}
FIRMWARE = {'7800bios.bin', 'supercharger.bin', 'highscor.rom', 'hsc.a78', 'bupchip.bin'}


def path_bytes(value, platform):
    namespace = PROFILES[platform][0]
    if not isinstance(value, str) or not value.startswith('/') or len(value.encode('utf8')) >= 256:
        raise ValueError('APF path must fit in 255 UTF-8 bytes')
    if '..' in PurePosixPath(value).parts or any(c in value for c in ('\\', ':', '\0')):
        raise ValueError('Unsafe APF path')
    if not any(value.startswith('/'+prefix+'/') for prefix in
               (f'Assets/{platform}/common', f'Assets/{namespace}/common', f'Saves/{namespace}/common')):
        raise ValueError('Path is outside declared platform assets')
    return value.encode('utf8').ljust(256, b'\0')


def cartridge(platform, path):
    size = path.stat().st_size
    if not 512 <= size <= 0x400000 or size % 4:
        raise ValueError('Native cartridge requires 512..4194304 bytes aligned to four bytes')
    with path.open('rb') as source:
        header = source.read(128)
    if path.suffix.lower() == '.a78':
        if header[1:10] != b'ATARI7800' or header[100:128] != b'ACTUAL CART DATA STARTS HERE':
            raise ValueError('Missing A78 cartridge header')
        declared = int.from_bytes(header[49:53], 'big')
        if declared != size - 128:
            raise ValueError('A78 header and actual payload length differ')
    return size


def pack(entries, platform, covers, warnings):
    base = 64 + len(entries)*1024
    pause = base + len(entries)*65536
    header = struct.pack('<4s5I', b'GBAF', 2, len(entries), base, pause, 65536).ljust(64, b'\0')
    rows, images, matched, missing = [], [], 0, 0
    font = shared.gb.font()
    for entry in entries:
        width, title, clipped, unknown = shared.gb.columns(entry['title'], font)
        subwidth, subtitle, _, _ = shared.gb.columns(NAMES[platform], font)
        if clipped or unknown:
            warnings.append({'path': entry['rom'], 'truncated': clipped, 'missing_glyphs': unknown})
        row = bytearray(1024)
        struct.pack_into('<4s7I', row, 0, b'ENT1', int(entry['folder']), entry.get('bytes', 0), 0, width, subwidth, 0, 0)
        for offset, key in ((32, 'rom'), (288, 'save'), (544, 'rtc')):
            row[offset:offset+256] = path_bytes(entry[key], platform)
        cover = covers/Path(entry['rom'].lstrip('/')).with_suffix('.png') if covers and not entry['folder'] else None
        if cover and cover.is_file():
            if not cover.resolve().is_relative_to(covers):
                raise ValueError('Cover escapes provided root')
            matched += 1
        else:
            cover = None
            if not entry['folder']:
                missing += 1
        art = shared.gb.picture(cover, entry['folder'], shared.kind(entry['title'])) if cover or entry['folder'] else shared.gb.title_card(entry['title'], platform, strict=False)
        rows.append(bytes(row))
        images.append((art+title+subtitle).ljust(65536, b'\0'))
    # Reserved F2 pause region is not used: exit via native Pocket Quit.
    return header+b''.join(rows+images)+bytes(153600), matched, missing


def build(platform, source, out, titles=None, covers=None):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists() or out.is_relative_to(source) or source.is_relative_to(out):
        raise ValueError('Fresh staging outside the source is required')
    namespace = PROFILES[platform][0]
    directory = shared.safe_path(source, f'Assets/{platform}/common')
    if not directory.is_dir():
        raise ValueError('Platform ROM directory is missing')
    aliases = shared.mapping(titles)
    covers = Path(covers).resolve() if covers else None
    if covers is not None and not covers.is_dir():
        raise ValueError('Cover root is missing')
    nodes = {'': {'name': NAMES[platform], 'parent': '', 'children': [], 'games': []}}
    refs, excluded, warnings = [], [], []

    def ensure(key):
        if key in nodes:
            return
        parent, _, leaf = key.rpartition('/')
        ensure(parent)
        label = '经典精选' if leaf == '0.FAVORITES' else shared.folder_label(leaf)
        nodes[key] = {'name': label, 'parent': parent, 'children': [], 'games': []}
        nodes[parent]['children'].append(key)

    for path in sorted(directory.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS[platform] or path.name.lower() in FIRMWARE:
            continue
        rel = path.relative_to(source).as_posix()
        shared.safe_path(source, rel)
        try:
            path_bytes('/'+rel, platform)
            size = cartridge(platform, path)
        except ValueError as error:
            excluded.append({'path': rel, 'reason': str(error)})
            continue
        digest = shared.gb.sha(path)
        tag = digest[:20]
        key = path.parent.relative_to(directory).as_posix()
        key = '' if key == '.' else key
        ensure(key)
        nodes[key]['games'].append({'title': aliases.get(rel, path.stem), 'folder': False, 'rom': '/'+rel, 'bytes': size,
            'save': f'/Saves/{namespace}/common/{tag}.sav', 'rtc': f'/Saves/{namespace}/common/{tag}.rtc'})
        refs.append({'path': rel, 'bytes': size, 'sha256': digest})
    if not refs:
        raise ValueError('No structurally supported cartridges')
    for key, node in list(nodes.items()):
        if len(node['children'])+len(node['games']) <= 127:
            continue
        games, node['games'] = node['games'], []
        for i in range(0, len(games), 127):
            child = (key+'/' if key else '')+f'@page{i//127+1}'
            if child in nodes:
                raise ValueError('Pagination name collides with existing directory')
            nodes[child] = {'name': f'第 {i//127+1} 页', 'parent': key, 'children': [], 'games': games[i:i+127]}
            node['children'].append(child)
        if len(node['children']) > 127:
            raise ValueError('More than 127 child folders at one level')
    ancestor = out.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    needed = sum(64+(1+len(n['children'])+len(n['games']))*66560+153600 for n in nodes.values())
    if shutil.disk_usage(ancestor).free < needed + 1024**2:
        raise ValueError('Insufficient local staging capacity')
    out.mkdir(parents=True)

    def page(key):
        return f'/Assets/{namespace}/common/libs/{hashlib.sha256(key.encode()).hexdigest()[:16]}.bin' if key else f'/Assets/{namespace}/common/menu.bin'

    def folder(key, title):
        return {'title': title, 'folder': True, 'rom': page(key), 'save': f'/Saves/{namespace}/common/'+('0'*20)+'.sav',
                'rtc': f'/Saves/{namespace}/common/'+('0'*20)+'.rtc'}

    if len({page(key) for key in nodes}) != len(nodes):
        raise ValueError('Page identity collision')
    files, hits, misses = [], 0, 0
    for key, node in nodes.items():
        entries = [folder(child, nodes[child]['name']) for child in sorted(node['children'])]+node['games']
        entries.append(folder(node['parent'], '返回上级' if key else '返回首页'))
        raw, matched, missing = pack(entries, platform, covers, warnings)
        rel = page(key)[1:]
        target = shared.safe_path(out, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        files.append({'path': rel, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        hits += matched
        misses += missing
    report = {'format': 'GBAF2/'+platform, 'files': files, 'source_refs': refs, 'excluded': excluded, 'warnings': warnings,
        'pages': len(nodes), 'game_refs': len(refs), 'cover_hits': hits, 'fallback_covers': misses,
        'source_writes': 0, 'rom_copies': 0, 'save_imports': 0,
        'saves': 'Native APF shared SaveKey/FA2/HSC files; no per-ROM save files generated', 'hardware_acceptance': 'pending'}
    (out/'library-manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    return report


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('platform', choices=PROFILES)
    for key in ('source', 'out'):
        cli.add_argument('--'+key, type=Path, required=True)
    cli.add_argument('--titles', type=Path)
    cli.add_argument('--covers', type=Path)
    args = cli.parse_args()
    result = build(args.platform, args.source, args.out, args.titles, args.covers)
    print(json.dumps({key: result[key] for key in ('pages', 'game_refs', 'cover_hits', 'fallback_covers')}))
