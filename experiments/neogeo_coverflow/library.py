#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile native NeoGeo APF instances into validated, read-only launch plans."""
import argparse
import hashlib
import importlib.util
import json
import re
import struct
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from install import safe_path

FORMAT = 'GBAF2/ng'
ASSETS = 'Assets/ngclab/common'
INSTANCE_ROOT = 'Assets/ng/Mazamars312.NeoGeo'
COMMON = 'Assets/ng/common'
BINDING = ASSETS + '/bindings.json'
BACKUP = 'Saves/ng/common/backup.bak'
# Fixed native slot order, bridge addresses, and physical capacity bounds.
SLOTS = ((1, 0x10a00000, 131072), (2, 0x50000000, 131072),
         (9, 0x10d00000, 131072), (3, 0x10c00000, 524288),
         (4, 0x10000000, 8388608), (5, 0x40000000, 67108864),
         (6, 0x10f80000, 524288), (7, 0x20000000, 16777216),
         (8, 0x10800000, 1048576), (0x101, 0x60000000, 8192),
         (0x102, 0x70000000, 65536))
BIOS = {1: 'uni-bios_4_0.rom', 2: '000-lo.lo', 9: 'sfix.sfix'}
CONTROL_MAX = {0xf0000024: 1, 0xf0000028: 1, 0xf000002c: 0xf,
               0xf0000030: 3, 0xf000003c: 0xffffff,
               0xf0000040: 3, 0xf000004c: 0xffffff,
               0xf0000050: 0xffffff, 0xf0000054: 7}
# The upstream APF decoder retains both address generations. Some shipped
# instances write all ones to the one-bit use_pcm register, whose upper bits
# are intentionally truncated by RTL; preserve those original uint32 writes.
CONTROL_ALIAS = {0xf0000308: 0xf0000050, 0xf000030c: 0xf0000028,
                 0xf0000310: 0xf000003c, 0xf0000314: 0xf000004c,
                 0xf0000400: 0xf0000054, 0xf0000404: 0xf0000024,
                 0xf0000408: 0xf000002c, 0xf000040c: 0xf0000030,
                 0xf0000410: 0xf0000040}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def uint(value):
    if isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]+', value):
        value = int(value, 16)
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        raise ValueError('Expected a uint32 value')
    return value


def relative(value):
    if not isinstance(value, str) or not value or len(value.encode('utf8')) >= 255:
        raise ValueError('Empty or oversized native path')
    if any(c in value for c in ('\\', ':', '\0')) or value.startswith('/'):
        raise ValueError('Native path must be relative')
    if any(p in ('', '.', '..') for p in value.split('/')):
        raise ValueError('Unsafe native path component')
    return value


def ref(root, rel):
    rel = relative(rel)
    p = safe_path(root, rel)
    if not p.is_file():
        raise ValueError('Missing native input: ' + rel)
    return {'path': rel, 'bytes': p.stat().st_size, 'sha256': digest(p)}


def instance_inputs(card, instance_path, hashes=True):
    card = Path(card).resolve()
    rel = relative(instance_path)
    prefix = next((p for p in (INSTANCE_ROOT, COMMON) if rel.startswith(p + '/')), None)
    if prefix is None or not rel.lower().endswith('.json'):
        raise ValueError('Expected a normal NeoGeo instance JSON')
    p = safe_path(card, rel)
    instance = json.loads(p.read_text(encoding='utf-8-sig'))['instance']
    if not isinstance(instance, dict) or instance.get('magic') != 'APF_VER_1':
        raise ValueError('Invalid native instance')
    if set(instance) - {'magic', 'data_path', 'data_slots', 'memory_writes', 'variant_select', 'core_select'}:
        raise ValueError('Unsupported instance option')
    for key in ('variant_select', 'core_select'):
        if key in instance:
            item = instance[key]
            uint(item['id'])
            if item['select'] is not False:
                raise ValueError('Instance must use the normal default NeoGeo bitstream')
    data_path = relative(instance['data_path'])
    folder = PurePosixPath(COMMON) if prefix == INSTANCE_ROOT else PurePosixPath(rel).parent
    folder = folder / data_path
    native = {}
    for row in instance['data_slots']:
        slot = uint(row['id'])
        if slot not in (3, 4, 5, 6, 7, 8) or slot in native or set(row) != {'id', 'filename'}:
            raise ValueError('Unsupported or duplicate native ROM slot')
        native[slot] = (folder / relative(row['filename'])).as_posix()
    if not {3, 4, 5, 6, 7}.issubset(native):
        raise ValueError('Native instance lacks a required ROM segment')
    native.update({slot: COMMON + '/' + name for slot, name in BIOS.items()})
    # Slot 0's filename/path determines the 8 KiB memory-card name. The backup
    # slot is explicitly common to the original ng platform, shared by games.
    memory = 'Saves/ng/Mazamars312.NeoGeo/' + PurePosixPath(rel[len(prefix) + 1:]).with_suffix('.sav').as_posix()
    native[0x101], native[0x102] = memory, BACKUP
    controls, registers = {}, set()
    for row in instance.get('memory_writes', []):
        if set(row) != {'address', 'data'}:
            raise ValueError('Unsupported native memory write')
        address, value = uint(row['address']), uint(row['data'])
        register = CONTROL_ALIAS.get(address, address)
        if register not in CONTROL_MAX or register in registers:
            raise ValueError('Unsupported native control register/value')
        registers.add(register)
        controls[address] = value
    rows = []
    for slot, address, maximum in SLOTS:
        if slot == 8 and slot not in native:
            rows.append({'slot': slot, 'address': address, 'bytes': 0, 'path': ''})
            continue
        name = native[slot]
        q = safe_path(card, name)
        exists = q.is_file()
        size = q.stat().st_size if exists else maximum
        if slot < 0x100 and (not exists or not 0 < size <= maximum or size % 4):
            raise ValueError('Missing or invalid native segment: ' + name)
        if slot >= 0x100 and q.exists() and (not exists or size != maximum):
            raise ValueError('Existing native save has wrong size: ' + name)
        row = {'slot': slot, 'address': address, 'path': name, 'bytes': size}
        if slot >= 0x100:
            row['exists'] = exists
        if hashes and exists:
            row['sha256'] = digest(q)
        rows.append(row)
    return {'instance': ref(card, rel) if hashes else {'path': rel, 'bytes': p.stat().st_size},
            'data_path': data_path, 'slots': rows,
            'controls': [{'address': a, 'data': v} for a, v in sorted(controls.items())]}


def _instances(card):
    card = Path(card).resolve()
    for base in (INSTANCE_ROOT, COMMON):
        for p in sorted(safe_path(card, base).rglob('*.json')):
            rel = p.relative_to(card).as_posix()
            yield rel


def available_instances(card):
    for rel in _instances(card):
        try:
            instance_inputs(card, rel, hashes=False)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        yield rel


def plan_bytes(plan):
    raw = bytearray(4096)
    struct.pack_into('<4s3I', raw, 0, b'NGP1', 1, 11, len(plan['controls']))
    for index, row in enumerate(plan['controls']):
        struct.pack_into('<II', raw, 64 + 8 * index, row['address'], row['data'])
    for index, row in enumerate(plan['slots']):
        offset = 256 + 272 * index
        struct.pack_into('<4I', raw, offset, row['slot'], row['address'], row['bytes'], 0)
        if row['path']:
            raw[offset + 16:offset + 272] = ('/' + relative(row['path'])).encode('utf8').ljust(256, b'\0')
    return bytes(raw)


def _path_bytes(value, platform='ng', namespace='ngclab'):
    if (platform, namespace) != ('ng', 'ngclab') or not value.startswith('/'):
        raise ValueError('Unexpected menu namespace')
    relative(value[1:])
    if not (value.startswith('/' + ASSETS + '/') or value.startswith('/Saves/ng/')):
        raise ValueError('Menu path outside native namespaces')
    return value.encode('utf8').ljust(256, b'\0')


def _shared():
    spec = importlib.util.spec_from_file_location('neogeo_atlas', ROOT / 'experiments/nes_coverflow/library.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.old.path_bytes = _path_bytes
    return module


def build(source, out, titles=None, covers=None):
    card, out = Path(source).resolve(), Path(out).resolve()
    if out.exists() or card.is_relative_to(out) or out.is_relative_to(card):
        raise ValueError('Use a fresh staging directory outside the source')
    shared = _shared()
    names = shared.mapping(titles)
    cover_root = Path(covers).resolve() if covers else None
    if cover_root is not None and not cover_root.is_dir():
        raise ValueError('Cover root is missing')
    plans, excluded = [], []
    for rel in _instances(card):
        try:
            plans.append(instance_inputs(card, rel))
        except (OSError, ValueError, KeyError, TypeError) as error:
            excluded.append({'path': rel, 'reason': str(error)})
    if not plans:
        raise ValueError('No complete native NeoGeo instances')
    source_refs, bios_refs, save_refs, instance_refs = {}, {}, {}, []
    for p in plans:
        instance_refs.append(p['instance'])
        for row in p['slots']:
            if not row['bytes']:
                continue
            target = save_refs if row['slot'] >= 0x100 else bios_refs if row['slot'] in BIOS else source_refs
            value = {k: v for k, v in row.items() if k not in ('address',)}
            if row['path'] in target and target[row['path']] != value:
                raise ValueError('Conflicting native file identities')
            target[row['path']] = value
    out.mkdir(parents=True)
    files, generated_plans, warnings = [], [], []
    def write(rel, raw):
        p = safe_path(out, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        entry = {'path': rel, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        files.append(entry)
        return entry
    nodes = {'': {'parent': '', 'name': 'NEOGEO 街机', 'children': [], 'games': []}}
    def ensure(key):
        if key in nodes:
            return
        parent, _, leaf = key.rpartition('/')
        ensure(parent)
        nodes[parent]['children'].append(key)
        nodes[key] = {'parent': parent, 'name': shared.folder_label(leaf), 'children': [], 'games': []}
    for p in plans:
        rel = p['instance']['path']
        tag = hashlib.sha256(rel.encode('utf8')).hexdigest()[:24]
        plan_path = ASSETS + '/plans/' + tag + '.ngp'
        entry = write(plan_path, plan_bytes(p))
        generated_plans.append(dict(entry, instance_path=rel, slots=p['slots'], controls=p['controls']))
        prefix = INSTANCE_ROOT if rel.startswith(INSTANCE_ROOT + '/') else COMMON
        key = PurePosixPath(rel[len(prefix) + 1:]).parent.as_posix()
        key = '' if key == '.' else key
        ensure(key)
        title = names.get(rel, Path(rel).stem)
        nodes[key]['games'].append({'title': title, 'folder': False, 'rom': '/' + plan_path,
            'bytes': 4096, 'save_bytes': 0, 'save': '/' + p['slots'][9]['path'],
            'rtc': '/' + BACKUP, 'cover_key': '/' + rel})
    for key, node in list(nodes.items()):
        if len(node['games']) + len(node['children']) <= 127:
            continue
        games, node['games'] = node['games'], []
        for i in range(0, len(games), 127):
            child = (key + '/' if key else '') + '@page' + str(i // 127 + 1)
            if child in nodes:
                raise ValueError('Pagination collides with native folder')
            nodes[child] = {'parent': key, 'name': '第 ' + str(i // 127 + 1) + ' 页', 'children': [], 'games': games[i:i + 127]}
            node['children'].append(child)
        if len(node['children']) > 127:
            raise ValueError('Too many folders')
    def page(key):
        return ASSETS + ('/libs/' + hashlib.sha256(key.encode()).hexdigest()[:16] + '.bin' if key else '/menu.bin')
    def folder(key, title):
        return {'title': title, 'folder': True, 'rom': '/' + page(key), 'save': '/' + BACKUP, 'rtc': '/' + BACKUP}
    hits, misses = 0, []
    for key, node in nodes.items():
        entries = [folder(child, nodes[child]['name']) for child in sorted(node['children'])] + node['games']
        entries.append(folder(node['parent'], '返回上级' if key else '返回首页'))
        raw, matched, missing = shared.pack(entries, cover_root, 'ng', 'NEOGEO 街机', namespace='ngclab', warnings=warnings)
        write(page(key), raw)
        hits += matched
        misses.extend(missing)
    menu_files = list(files)
    binding = {'format': FORMAT, 'source_refs': list(source_refs.values()), 'bios_refs': list(bios_refs.values()),
               'instance_refs': instance_refs, 'native_save_refs': list(save_refs.values()),
               'plans': generated_plans, 'menu_files': menu_files}
    write(BINDING, (json.dumps(binding, ensure_ascii=False, indent=2) + '\n').encode('utf8'))
    for row in save_refs.values():
        if not row['exists']:
            write(row['path'], b'\xff' * row['bytes'])
    result = dict(binding, files=files, pages=len(nodes), game_refs=len(plans), cover_hits=hits,
                  fallback_covers=len(misses), warnings=warnings, excluded=excluded, source_writes=0,
                  rom_copies=0, save_imports=0, hardware_acceptance='pending')
    validate_manifest(card, result)
    validate_pages(out, result)
    (out / 'library-manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return result


def validate_manifest(card, manifest):
    card = Path(card).resolve()
    if manifest.get('format') != FORMAT:
        raise ValueError('Unexpected NeoGeo menu format')
    # Derive the entire closure again from native inputs, including both save
    # roles. A path/name supplied only by the manifest never authorizes a write.
    derived = [instance_inputs(card, row['path']) for row in manifest['instance_refs']]
    if len(derived) != len({p['instance']['path'] for p in derived}):
        raise ValueError('Duplicate native instance')
    guards, saves, sources, bios = {}, {}, {}, {}
    for p in derived:
        guards[p['instance']['path']] = p['instance']
        for row in p['slots']:
            if not row['bytes']:
                continue
            q = {k: v for k, v in row.items() if k != 'address'}
            if row['slot'] >= 0x100:
                saves[row['path']] = q
                if row['exists']:
                    guards[row['path']] = {k: row[k] for k in ('path', 'bytes', 'sha256')}
            elif row['slot'] in BIOS:
                bios[row['path']] = q
                guards[row['path']] = {k: row[k] for k in ('path', 'bytes', 'sha256')}
            else:
                sources[row['path']] = q
    def mapped(name):
        rows = manifest[name]
        if len(rows) != len({r['path'] for r in rows}):
            raise ValueError('Duplicate manifest reference')
        return {r['path']: r for r in rows}
    if sources != mapped('source_refs') or bios != mapped('bios_refs'):
        raise ValueError('Native instance ROM/BIOS closure changed')
    if saves != mapped('native_save_refs') or {p['instance']['path']: p['instance'] for p in derived} != mapped('instance_refs'):
        raise ValueError('Native instance/save mapping changed')
    expected_plans = {p['instance']['path']: p for p in derived}
    if len(manifest['plans']) != len(expected_plans):
        raise ValueError('Incomplete native launch-plan set')
    for p in manifest['plans']:
        expected = expected_plans.pop(p['instance_path'])
        raw = plan_bytes(expected)
        expected_path = ASSETS + '/plans/' + hashlib.sha256(p['instance_path'].encode('utf8')).hexdigest()[:24] + '.ngp'
        if p['path'] != expected_path or p['slots'] != expected['slots'] or p['controls'] != expected['controls'] or p['sha256'] != hashlib.sha256(raw).hexdigest() or p['bytes'] != len(raw):
            raise ValueError('Native launch plan changed')
    return {'guards': list(guards.values()), 'save_paths': {p: r['bytes'] for p, r in saves.items()}, 'bios_files': {}}


def validate_pages(root, manifest):
    root = Path(root).resolve()
    if manifest.get('format') != FORMAT:
        raise ValueError('Unexpected NeoGeo menu format')
    files = {r['path']: r for r in manifest['menu_files']}
    if len(files) != len(manifest['menu_files']):
        raise ValueError('Duplicate menu output')
    plans = {r['path']: r for r in manifest['plans']}
    if len(plans) != len(manifest['plans']):
        raise ValueError('Duplicate native launch plan')
    pages = {p for p in files if p.endswith('.bin')}
    if ASSETS + '/menu.bin' not in pages or set(files) != pages | plans.keys():
        raise ValueError('Unexpected generated menu files')
    for path, row in files.items():
        suffix = path.removeprefix(ASSETS + '/')
        if not path.startswith(ASSETS + '/') or not (suffix == 'menu.bin' or re.fullmatch(r'libs/[0-9a-f]{16}\.bin|plans/[0-9a-f]{24}\.ngp', suffix)):
            raise ValueError('Menu output outside namespace')
        p = safe_path(root, path)
        if p.stat().st_size != row['bytes'] or digest(p) != row['sha256']:
            raise ValueError('Generated menu content changed: ' + path)
    for path, p in plans.items():
        if {k: p[k] for k in ('path', 'bytes', 'sha256')} != files[path]:
            raise ValueError('Launch plan file identity changed')
        if safe_path(root, path).read_bytes() != plan_bytes(p):
            raise ValueError('Launch plan does not match native references')
    # During staging only missing native saves may be emitted, using the exact
    # original 0xFF power-on contents. Installed binding files omit this list,
    # since ordinary gameplay legitimately changes save contents afterward.
    if 'files' in manifest:
        seeds = {r['path']: r for r in manifest['native_save_refs'] if not r['exists']}
        emitted = {r['path']: r for r in manifest['files']}
        if len(emitted) != len(manifest['files']) or set(emitted) != set(files) | {BINDING} | seeds.keys():
            raise ValueError('Unexpected staged file or missing native seed')
        for path, row in files.items():
            if emitted[path] != row:
                raise ValueError('Staged menu identity mismatch')
        for path, row in seeds.items():
            raw = b'\xff' * row['bytes']
            if safe_path(root, path).read_bytes() != raw or emitted[path] != {'path': path, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}:
                raise ValueError('Native seed differs from original empty format')
        binding_path = safe_path(root, BINDING)
        expected_binding = {key: manifest[key] for key in ('format', 'source_refs', 'bios_refs', 'instance_refs', 'native_save_refs', 'plans', 'menu_files')}
        if json.loads(binding_path.read_text(encoding='utf8')) != expected_binding or ref(root, BINDING) != emitted[BINDING]:
            raise ValueError('Staged binding differs from the validated library')
    edges, seen_games = {}, set()
    def field(row, start):
        raw = row[start:start + 256]
        value, separator, padding = raw.partition(b'\0')
        if not separator or any(padding):
            raise ValueError('Noncanonical menu path field')
        value = value.decode('utf8')
        if not value.startswith('/'):
            raise ValueError('Menu path must be absolute within SD')
        return relative(value[1:])
    for path in pages:
        raw = safe_path(root, path).read_bytes()
        magic, version, count, base, pause, stride = struct.unpack_from('<4s5I', raw)
        if magic != b'GBAF' or version != 2 or not 1 <= count <= 128 or base != 64 + count * 1024 or pause != base + count * 65536 or stride != 65536 or len(raw) != pause + 153600:
            raise ValueError('Invalid NeoGeo page geometry')
        edges[path] = []
        for index in range(count):
            row = raw[64 + index * 1024:64 + (index + 1) * 1024]
            tag, kind, size = struct.unpack_from('<4s2I', row)
            target, card_save, backup = (field(row, offset) for offset in (32, 288, 544))
            if tag != b'ENT1' or kind not in (0, 1) or index == count - 1 and kind != 1:
                raise ValueError('Invalid NeoGeo page record')
            if kind:
                if target not in pages or card_save != BACKUP or backup != BACKUP:
                    raise ValueError('Page links outside generated library')
                edges[path].append(target)
            else:
                if target not in plans or size != 4096 or card_save != plans[target]['slots'][9]['path'] or backup != BACKUP:
                    raise ValueError('Game record changed native save or plan binding')
                seen_games.add(target)
    reached, pending = set(), [ASSETS + '/menu.bin']
    while pending:
        node = pending.pop()
        if node not in reached:
            reached.add(node)
            pending.extend(edges[node])
    if reached != pages or seen_games != plans.keys():
        raise ValueError('Unreachable page or missing native game')
    return {'pages': len(pages), 'plans': len(plans)}


def existing(card, refs=None):
    card = Path(card).resolve()
    path = safe_path(card, BINDING)
    if not path.exists():
        if safe_path(card, ASSETS + '/menu.bin').exists():
            raise ValueError('Existing NeoGeo menu lacks its native bindings')
        return []
    binding = json.loads(path.read_text(encoding='utf8'))
    validate_pages(card, binding)
    # Save contents legitimately change during play. Re-derive their current
    # identities while retaining every original instance-to-slot binding.
    fresh = [instance_inputs(card, r['path']) for r in binding['instance_refs']]
    current_saves = {r['path']: {k: v for k, v in r.items() if k != 'address'}
                     for p in fresh for r in p['slots'] if r['slot'] >= 0x100}
    old_saves = {r['path']: r for r in binding['native_save_refs']}
    if {p: r['bytes'] for p, r in current_saves.items()} != {p: r['bytes'] for p, r in old_saves.items()}:
        raise ValueError('Existing native save mapping changed')
    binding['native_save_refs'] = list(current_saves.values())
    for p in binding['plans']:
        for row in p['slots']:
            if row['slot'] >= 0x100:
                row.update(current_saves[row['path']])
    checked = validate_manifest(card, binding)
    if refs is not None:
        new = {r['path']: r for r in refs}
        for row in binding['source_refs']:
            if row['path'] in new and (new[row['path']]['bytes'], new[row['path']]['sha256']) != (row['bytes'], row['sha256']):
                raise ValueError('Changed native ROM cannot inherit an existing instance save silently')
    return ([ref(card, BINDING)] + [ref(card, r['path']) for r in binding['menu_files']]
            + [{k: r[k] for k in ('path', 'bytes', 'sha256')} for r in binding['source_refs']]
            + checked['guards'])


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'out'):
        cli.add_argument('--' + name, required=True, type=Path)
    for name in ('titles', 'covers'):
        cli.add_argument('--' + name, type=Path)
    a = cli.parse_args()
    result = build(a.source, a.out, a.titles, a.covers)
    print(json.dumps({k: result[k] for k in ('pages', 'game_refs', 'cover_hits', 'fallback_covers')}))
