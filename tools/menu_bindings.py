# SPDX-License-Identifier: MIT
"""Validate filename-built menus and retain existing native save/cheat bindings."""
import hashlib
from pathlib import Path
import re
import struct

from install import safe_path


def profile(system):
    return {'GB-GBC': ('gbclab', 'covers.bin'), 'GBA': ('gbalab', 'menu.bin'), 'NES': ('neslab', 'menu.bin'),
            'GG': ('ggclab', 'menu.bin'), 'SMS': ('smslab', 'menu.bin'),
            'SG1000': ('sgclab', 'menu.bin')}[system]


def page(raw, system, menu_format):
    if system == 'GB-GBC':
        from style_library import decode
        decoded = decode(raw)
        return [{'folder': bool(e['record'][40] & 128), 'paths': e['paths'],
                 'bytes': int.from_bytes(e['record'][44:48], 'little')} for e in decoded['entries']]
    if len(raw) < 64:
        raise ValueError('Truncated native CoverFlow menu')
    magic, version, count, art, pause, stride = struct.unpack_from('<4s5I', raw)
    expected = 2 if menu_format == 'GBAF2' else 1
    maximum = 128 if expected == 2 and system != 'NES' else 2047
    texture = 65536 if expected == 2 else 76800
    if (magic != b'GBAF' or version != expected or not 1 <= count <= maximum
            or art != 64 + count*1024 or pause != art + count*texture
            or stride != (65536 if expected == 2 else 0) or len(raw) != pause + 153600):
        raise ValueError('Native menu layout/format differs')
    entries = []
    for i in range(count):
        row = raw[64+i*1024:64+(i+1)*1024]
        folder = int.from_bytes(row[4:8], 'little')
        if row[:4] != b'ENT1' or folder not in (0, 1):
            raise ValueError('Invalid native CoverFlow entry')
        paths = []
        for offset in (32, 288, 544):
            field = row[offset:offset+256]
            value = field.split(b'\0', 1)[0].decode('utf8')
            if not 0 < len(value.encode('utf8')) < 256 or field != value.encode('utf8').ljust(256, b'\0'):
                raise ValueError('Noncanonical native menu path')
            paths.append(value)
        entries.append({'folder': bool(folder), 'paths': paths, 'bytes': int.from_bytes(row[8:12], 'little'),
                        'cheat_bytes': int.from_bytes(row[16:20], 'little') if system in ('GG', 'SMS', 'SG1000') else 0})
    if not entries[-1]['folder']:
        raise ValueError('Final parent entry must be a folder')
    return entries


def owned_path(root, value, prefix):
    if not value.startswith('/' + prefix):
        raise ValueError('Menu path outside its namespace: ' + value)
    return safe_path(root, value[1:])


def page_links(root, relative, raw, entries, system):
    ns, leaf = profile(system)
    prefix = 'Assets/' + ns + '/common/'
    progress = 'Saves/' + ns + '/common/'
    for entry in entries:
        owned_path(root, entry['paths'][1], progress)
        owned_path(root, entry['paths'][2], 'Assets/'+ns+'/cheat/' if system in ('GG', 'SMS', 'SG1000') else progress)
        if entry['folder']:
            owned_path(root, entry['paths'][0], prefix)
    if system == 'GB-GBC':
        ident = 'root' if relative == prefix + leaf else Path(relative).stem
        expected = [f'/{progress}meta/{ident}.log', f'/{progress}meta/{ident}.cfg']
        if raw[-512:] != b''.join(v.encode('utf8').ljust(256, b'\0') for v in expected):
            raise ValueError('GB/GBC metadata path differs')


def validate(root, manifest, system, menu_format=None):
    """Require complete reachable pages and content-bound ordinary save paths."""
    root = Path(root)
    ns, leaf = profile(system)
    prefix = 'Assets/' + ns + '/common/'
    refs = manifest['roms' if system == 'GBA' else 'source_refs']
    by_name = {r['path']: r for r in refs}
    if not refs or len({p.casefold() for p in by_name}) != len(refs):
        raise ValueError('Empty or duplicate ROM identities')
    paths = {r['path'] for r in manifest['files'] if r['path'].startswith(prefix) and r['path'] != prefix + 'gbc_bios.bin'}
    links, games = {}, set()
    for relative in paths:
        if not re.fullmatch(re.escape(prefix) + '(?:' + re.escape(leaf) + r'|libs/[0-9a-f]{16}\.bin)', relative):
            raise ValueError('Unexpected menu page: ' + relative)
        raw = safe_path(root, relative).read_bytes()
        entries = page(raw, system, menu_format)
        page_links(root, relative, raw, entries, system)
        links[relative] = set()
        for entry in entries:
            name = entry['paths'][0].removeprefix('/')
            if entry['folder']:
                if name not in paths:
                    raise ValueError('Broken menu category link')
                links[relative].add(name)
                continue
            ref = by_name.get(name)
            if ref is None or entry['paths'][0] != '/' + name or entry['bytes'] != ref['bytes']:
                raise ValueError('Menu ROM identity missing')
            tag = ref['sha256'][:20]
            suffix = 'sus' if system == 'GB-GBC' else 'rtc'
            expected = [f'/Saves/{ns}/common/{tag}.sav', f'/Saves/{ns}/common/{tag}.{suffix}']
            if entry['paths'][1:] != expected:
                raise ValueError('Menu ordinary save identity differs')
            games.add(ref['sha256'])
    visited, todo = set(), [prefix + leaf]
    while todo:
        name = todo.pop()
        if name in visited:
            continue
        if name not in links:
            raise ValueError('Missing root menu')
        visited.add(name)
        todo.extend(links[name] - visited)
    if visited != paths or games != {r['sha256'] for r in refs}:
        raise ValueError('Unreachable menu page or missing game content')


def existing(card, system, new_cheats=None, refs=None):
    """Guard old pages and refuse an automatic switch away from played save IDs."""
    card = Path(card)
    ns, leaf = profile(system)
    # Callers have already verified these bytes; sealing and apply recheck them.
    known = {r['path']: r['sha256'] for r in refs or ()}
    prefix = 'Assets/' + ns + '/common/'
    todo, guards = [prefix + leaf], {}
    sega = system in ('GG', 'SMS', 'SG1000')
    suffix = 'sus' if system == 'GB-GBC' else 'rtc'
    while todo:
        relative = todo.pop()
        if relative in guards:
            continue
        if not re.fullmatch(re.escape(prefix) + '(?:' + re.escape(leaf) + r'|libs/[0-9a-f]{16}\.bin)', relative):
            raise ValueError('Existing category link escapes menu pages')
        path = safe_path(card, relative)
        raw = path.read_bytes()
        entries = page(raw, system, 'GBAF2')
        page_links(card, relative, raw, entries, system)
        guards[relative] = {'path': relative, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        for entry in entries:
            if entry['folder']:
                todo.append(entry['paths'][0][1:])
                continue
            save = entry['paths'][1]
            match = re.fullmatch(r'/Saves/' + ns + r'/common/([0-9a-f]{20})\.sav', save)
            other = '/Assets/'+ns+'/cheat/'+match[1]+'.cht' if match and sega else save[:-3] + suffix
            if not match or entry['paths'][2] != other:
                raise ValueError('Existing legacy save IDs need an explicit migration; keep the current menu')
            platforms = ('gb', 'gbc') if system == 'GB-GBC' else (system.lower(),)
            if not entry['paths'][0].startswith(tuple('/Assets/' + p + '/common/' for p in platforms)):
                raise ValueError('Existing ROM link escapes the platform')
            rom = safe_path(card, entry['paths'][0][1:])
            if rom.is_file() and (known.get(entry['paths'][0][1:]) or hashlib.sha256(rom.read_bytes()).hexdigest())[:20] != match[1]:
                raise ValueError('Existing ROM content or save identity changed; preserve its progress before migration')
            if sega and entry['cheat_bytes'] and match[1] in (new_cheats or {}):
                if not new_cheats[match[1]]:
                    raise ValueError('Existing matched cheats would be disabled; rebuild with the matching --cheats index')
                cheat = safe_path(card, other[1:])
                if cheat.exists():
                    guards[other[1:]] = {'path': other[1:], 'bytes': cheat.stat().st_size,
                                        'sha256': hashlib.sha256(cheat.read_bytes()).hexdigest()}
    return list(guards.values())
