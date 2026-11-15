# SPDX-License-Identifier: MIT
"""Validate filename-built menus and retain existing native save/cheat bindings."""
import hashlib
from pathlib import Path
import re
import struct

from install import safe_path
import additional_menus


def profile(system):
    if system in additional_menus.PROFILES:
        return additional_menus.PROFILES[system]['namespace'], 'menu.bin'
    return {'GB-GBC': ('gbclab', 'covers.bin'), 'GBA': ('gbalab', 'menu.bin'), 'NES': ('neslab', 'menu.bin'),
            'GG': ('ggclab', 'menu.bin'), 'SMS': ('smslab', 'menu.bin'),
            'SG1000': ('sgclab', 'menu.bin'), 'PCE': ('pcelab', 'menu.bin'), 'MD': ('mdclab', 'menu.bin'),
            'SFC': ('snescn', 'menu.bin'), 'CPS2': ('cpslab', 'menu.bin')}[system]


def page(raw, system, menu_format, gb_cheats=False):
    if system == 'GB-GBC':
        from style_library import decode
        decoded = decode(raw, allow_cheats=gb_cheats)
        return [{'folder': bool(e['record'][40] & 128), 'paths': e['paths'],
                 'bytes': int.from_bytes(e['record'][44:48], 'little'),
                 'cheat_path': e.get('cheat_path', ''), 'cheat_bytes': e.get('cheat_bytes', 0)}
                for e in decoded['entries']]
    if len(raw) < 64:
        raise ValueError('Truncated native CoverFlow menu')
    magic, version, count, art, pause, stride = struct.unpack_from('<4s5I', raw)
    expected = 2 if menu_format == 'GBAF2' else 1
    maximum = 128 if expected == 2 and system != 'NES' else 2047
    texture = 65536 if expected == 2 else 76800
    compact = system in ('SUPERVISION', 'ARDUBOY')
    if (magic != b'GBAF' or version != expected or not 1 <= count <= maximum
            or art != 64 + count*1024 or pause != art + count*texture
            or stride != (65536 if expected == 2 else 0) or len(raw) != pause + (0 if compact else 153600)):
        raise ValueError('Native menu layout/format differs')
    entries = []
    for i in range(count):
        row = raw[64+i*1024:64+(i+1)*1024]
        folder = int.from_bytes(row[4:8], 'little')
        if row[:4] != b'ENT1' or folder not in (0, 1):
            raise ValueError('Invalid native CoverFlow entry')
        paths = []
        used_paths = (2 if system == 'ARDUBOY' and not folder else 1) if compact else 3
        for number, offset in enumerate((32, 288, 544)):
            field = row[offset:offset+256]
            if number >= used_paths:
                if field != bytes(256):
                    raise ValueError('Unused native path must be empty')
                paths.append('')
                continue
            value = field.split(b'\0', 1)[0].decode('utf8')
            if not 0 < len(value.encode('utf8')) < 256 or field != value.encode('utf8').ljust(256, b'\0'):
                raise ValueError('Noncanonical native menu path')
            paths.append(value)
        entries.append({'folder': bool(folder), 'paths': paths, 'bytes': int.from_bytes(row[8:12], 'little'),
                        'cheat_bytes': int.from_bytes(row[16:20], 'little') if system in ('NES', 'GG', 'SMS', 'SG1000') else 0})
        if system in ('PCE', 'MD'):
            entries[-1]['cart_mode'] = int.from_bytes(row[12:16], 'little')
        elif system == 'ARDUBOY':
            entries[-1]['program_bytes'] = int.from_bytes(row[12:16], 'little')
        elif system=='SFC':
            entries[-1]['sfc_layout'] = struct.unpack_from('<III',row,12)
        elif system=='CPS2' or system in additional_menus.CPS_SYSTEMS:
            entries[-1]['cps_settings'] = (*struct.unpack_from('<II',row,16),struct.unpack_from('<I',row,800)[0])
        if system in ('PCE','MD','SFC'):
            entries[-1]['cheat_bytes'] = int.from_bytes(row[804:808], 'little')
    if not entries[-1]['folder']:
        raise ValueError('Final parent entry must be a folder')
    return entries


def owned_path(root, value, prefix):
    if not value.startswith('/' + prefix):
        raise ValueError('Menu path outside its namespace: ' + value)
    return safe_path(root, value[1:])


def page_links(root, relative, raw, entries, system, native_cheats=False):
    ns, leaf = profile(system)
    prefix = 'Assets/' + ns + '/common/'
    progress = 'Saves/' + ns + '/common/'
    for entry in entries:
        if entry['paths'][1]:
            owned_path(root, entry['paths'][1], progress)
        if entry['paths'][2]:
            owned_path(root, entry['paths'][2], 'Assets/'+ns+'/cheat/' if native_cheats or system in ('GG', 'SMS', 'SG1000') else progress)
        if entry['folder']:
            owned_path(root, entry['paths'][0], prefix)
    if system == 'GB-GBC':
        ident = 'root' if relative == prefix + leaf else Path(relative).stem
        expected = [f'/{progress}meta/{ident}.log', f'/{progress}meta/{ident}.cfg']
        tail = 1040 + len(entries)*(128+65536+768)
        if raw[tail-512:tail] != b''.join(v.encode('utf8').ljust(256, b'\0') for v in expected):
            raise ValueError('GB/GBC metadata path differs')


def cps_bindings(manifest):
    """Group runtime identities while retaining every source JSON and ROM path."""
    refs = {row['path']: row for row in manifest['source_refs']}
    sources, bindings = set(), {}
    for row in manifest.get('instances', []):
        source = row['path'].casefold()
        if source in sources:
            raise ValueError('Duplicate CPS instance source')
        sources.add(source)
        ref = refs.get(row['rom_path'])
        settings = {key: row[key] for key in ('core_mode', 'button_map', 'dip_switches')}
        if ref is None or any(type(v) is not int or not 0 <= v <= 0xffffffff for v in settings.values()):
            raise ValueError('Invalid CPS instance ROM/settings')
        digest = ref['sha256']
        if not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid CPS ROM digest')
        tag = hashlib.sha256(bytes.fromhex(digest)+struct.pack('<III', *settings.values())).hexdigest()[:20]
        if row['save_tag'] != tag:
            raise ValueError('CPS save identity differs from ROM/settings')
        bound = bindings.setdefault(tag, {'save_tag': tag, 'rom_sha256': digest,
            **settings, 'rom_paths': [], 'instance_paths': []})
        if bound['rom_sha256'] != digest or any(bound[k] != v for k,v in settings.items()):
            raise ValueError('Conflicting CPS runtime identity')
        if row['rom_path'] not in bound['rom_paths']:
            bound['rom_paths'].append(row['rom_path'])
        bound['instance_paths'].append(row['path'])
    for bound in bindings.values():
        bound['rom_paths'].sort()
        bound['instance_paths'].sort()
    return [bindings[tag] for tag in sorted(bindings)]


def validate(root, manifest, system, menu_format=None):
    """Require complete reachable pages and content-bound ordinary save paths."""
    if system == 'NEOGEO':
        return additional_menus.instance_module(system).validate_pages(root, manifest)
    root = Path(root)
    ns, leaf = profile(system)
    native_platform={'NES':'nes','PCE':'pce','MD':'genesis','SFC':'snes'}.get(system)
    native_cheats = native_platform is not None and manifest.get('features') == ['PLCH1']
    gb_cheats = system == 'GB-GBC' and manifest.get('features') == ['PLCH1']
    prefix = 'Assets/' + ns + '/common/'
    refs = manifest['roms' if system == 'GBA' else 'source_refs']
    by_name = {r['path']: r for r in refs}
    if not refs or len({p.casefold() for p in by_name}) != len(refs):
        raise ValueError('Empty or duplicate ROM identities')
    cps = system == 'CPS2' or system in additional_menus.CPS_SYSTEMS
    bindings = cps_bindings(manifest) if cps else []
    if cps and manifest.get('runtime_bindings', bindings) != bindings:
        raise ValueError('CPS runtime binding inventory differs')
    instances = {(path,row['save_tag']):row for row in bindings for path in row['rom_paths']}
    paths = {r['path'] for r in manifest['files'] if r['path'].startswith(prefix) and r['path'] != prefix + 'gbc_bios.bin'}
    if system == 'WS':
        paths -= {prefix+'bw.rom', prefix+'color.rom'}
    links, games, cheat_files = {}, set(), set()
    for relative in paths:
        if not re.fullmatch(re.escape(prefix) + '(?:' + re.escape(leaf) + r'|libs/[0-9a-f]{16}\.bin)', relative):
            raise ValueError('Unexpected menu page: ' + relative)
        raw = safe_path(root, relative).read_bytes()
        entries = page(raw, system, menu_format, gb_cheats)
        page_links(root, relative, raw, entries, system, native_cheats)
        links[relative] = set()
        for entry in entries:
            name = entry['paths'][0].removeprefix('/')
            if entry['folder']:
                if name not in paths:
                    raise ValueError('Broken menu category link')
                links[relative].add(name)
                continue
            ref = by_name.get(name)
            if ref is None or entry['paths'][0] != '/' + name or entry['bytes'] != ref['bytes']-ref.get('rom_offset',0):
                raise ValueError('Menu ROM identity missing')
            if system in ('PCE', 'MD'):
                mode = int(system == 'PCE' and Path(name).suffix.lower() == '.sgx')
                if entry['cart_mode'] != mode or ref.get('config') != mode:
                    raise ValueError('Menu cartridge mode differs')
            elif system=='SFC' and entry['sfc_layout']!=(ref['save_bytes'],ref['rom_offset'],ref['config']):
                raise ValueError('SNES menu header decision differs')
            elif system == 'ARDUBOY' and entry['program_bytes'] != ref['program_bytes']:
                raise ValueError('Arduboy decoded program length differs')
            tag = ref['sha256'][:20]
            if cps:
                tag = Path(entry['paths'][1]).stem
                variant = instances.get((name,tag))
                if variant is None or entry['cps_settings']!=tuple(variant[k] for k in ('core_mode','button_map','dip_switches')):
                    raise ValueError('CPS menu configuration differs from its instance')
            suffix = 'sus' if system == 'GB-GBC' else 'rtc'
            expected = [f'/Saves/{ns}/common/{tag}.sav', f'/Saves/{ns}/common/{tag}.{suffix}']
            if system == 'SUPERVISION':
                expected = ['', '']
            elif system == 'ARDUBOY':
                expected[1] = ''
            if native_cheats:
                expected[1] = f'/Assets/{ns}/cheat/{tag}.cht'
                if entry['cheat_bytes']:
                    from native_cheats import decode as decode_cheats
                    cheat = safe_path(root, expected[1][1:]).read_bytes()
                    if len(cheat) != entry['cheat_bytes']:
                        raise ValueError('Native cheat length differs')
                    decode_cheats(cheat, native_platform, ref['sha256'])
            if gb_cheats and entry['cheat_bytes']:
                from native_cheats import decode as decode_cheats
                relative_cheat = f'Assets/{ns}/cheat/{tag}.cht'
                if entry['cheat_path'] != '/'+relative_cheat:
                    raise ValueError('GB/GBC cheat ROM identity differs')
                cheat = safe_path(root, relative_cheat).read_bytes()
                if len(cheat) != entry['cheat_bytes']:
                    raise ValueError('GB/GBC cheat length differs')
                platform = 'gbc' if int.from_bytes(cheat[4:8], 'little') == 0x10002 else 'gb'
                decode_cheats(cheat, platform, ref['sha256'])
                cheat_files.add(relative_cheat)
            if entry['paths'][1:] != expected:
                raise ValueError('Menu ordinary save identity differs')
            games.add(tag if cps else ref['sha256'])
    visited, todo = set(), [prefix + leaf]
    while todo:
        name = todo.pop()
        if name in visited:
            continue
        if name not in links:
            raise ValueError('Missing root menu')
        visited.add(name)
        todo.extend(links[name] - visited)
    expected_games = {row['save_tag'] for row in bindings} if cps else {r['sha256'] for r in refs}
    if visited != paths or games != expected_games:
        raise ValueError('Unreachable menu page or missing game content')
    if gb_cheats and cheat_files != {row['path'] for row in manifest['files'] if row['path'].endswith('.cht')}:
        raise ValueError('GB/GBC cheat manifest differs from reachable pages')


def existing(card, system, new_cheats=None, refs=None, cps_save_id=None, *, menu_format='GBAF2'):
    """Guard old pages and refuse an automatic switch away from played save IDs."""
    if system == 'NEOGEO':
        return additional_menus.instance_module(system).existing(card, refs=refs)
    card = Path(card)
    ns, leaf = profile(system)
    # Callers have already verified these bytes; sealing and apply recheck them.
    known = {r['path']: r['sha256'] for r in refs or ()}
    prefix = 'Assets/' + ns + '/common/'
    todo, guards = [prefix + leaf], {}
    sega = system in ('GG', 'SMS', 'SG1000')
    native_cheats = False
    if system in ('GB-GBC','NES','PCE','MD','SFC'):
        import delivery
        from core_candidates import CATALOG
        short,_,platform=delivery.PROFILES[system]
        binary = safe_path(card, f'Cores/pocketlab.{short}/{platform}.rbf_r')
        if binary.is_file():
            candidate = CATALOG.get(system, {}).get(hashlib.sha256(binary.read_bytes()).hexdigest(), {})
            native_cheats = 'PLCH1' in candidate.get('features', [])
    gb_cheats = system == 'GB-GBC' and native_cheats
    if gb_cheats:
        native_cheats = False
    suffix = 'sus' if system == 'GB-GBC' else 'rtc'
    while todo:
        relative = todo.pop()
        if relative in guards:
            continue
        if not re.fullmatch(re.escape(prefix) + '(?:' + re.escape(leaf) + r'|libs/[0-9a-f]{16}\.bin)', relative):
            raise ValueError('Existing category link escapes menu pages')
        path = safe_path(card, relative)
        raw = path.read_bytes()
        entries = page(raw, system, menu_format, gb_cheats)
        page_links(card, relative, raw, entries, system, native_cheats)
        guards[relative] = {'path': relative, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        for entry in entries:
            if entry['folder']:
                todo.append(entry['paths'][0][1:])
                continue
            platforms = ('gb', 'gbc') if system == 'GB-GBC' else ({'MD':'genesis','SFC':'snes','CPS2':'jtcps2'}.get(system,system.lower()),)
            if system in additional_menus.PROFILES:
                platforms = (additional_menus.PROFILES[system]['platform'],)
            if not entry['paths'][0].startswith(tuple('/Assets/' + p + '/common/' for p in platforms)):
                raise ValueError('Existing ROM link escapes the platform')
            if system == 'SUPERVISION':
                continue
            save = entry['paths'][1]
            match = re.fullmatch(r'/Saves/' + ns + r'/common/([0-9a-f]{20})\.sav', save)
            other = '/Assets/'+ns+'/cheat/'+match[1]+'.cht' if match and (sega or native_cheats) else save[:-3] + suffix
            if system == 'ARDUBOY':
                other = ''
            if not match or entry['paths'][2] != other:
                raise ValueError('Existing legacy save IDs need an explicit migration; keep the current menu')
            rom = safe_path(card, entry['paths'][0][1:])
            if rom.is_file():
                digest = known.get(entry['paths'][0][1:]) or hashlib.sha256(rom.read_bytes()).hexdigest()
                cps = system == 'CPS2' or system in additional_menus.CPS_SYSTEMS
                tag = cps_save_id(digest,*entry['cps_settings']) if cps else digest[:20]
                if tag != match[1]:
                    raise ValueError('Existing ROM content or save identity changed; preserve its progress before migration')
            if gb_cheats and entry['cheat_bytes']:
                other = f'/Assets/{ns}/cheat/{match[1]}.cht'
                if entry['cheat_path'] != other:
                    raise ValueError('Existing GB/GBC cheat identity differs')
            if (sega or native_cheats or gb_cheats) and entry['cheat_bytes'] and match[1] in (new_cheats or {}):
                if not new_cheats[match[1]]:
                    raise ValueError('Existing matched cheats would be disabled; rebuild with the matching --cheats index')
                cheat = safe_path(card, other[1:])
                if cheat.exists():
                    guards[other[1:]] = {'path': other[1:], 'bytes': cheat.stat().st_size,
                                        'sha256': hashlib.sha256(cheat.read_bytes()).hexdigest()}
    return list(guards.values())
