# SPDX-License-Identifier: MIT
"""Contracts for additional native menus and their guarded first installation."""
import json
from pathlib import Path

PROFILES = {
    'WS': dict(short='WSCoverFlow', namespace='wsclab', platform='wonderswan', binary='wswan',
               family='ws_coverflow', label='WonderSwan / Color', extensions={'.ws', '.wsc'}),
    'SUPERVISION': dict(short='Supervision', namespace='svclab', platform='supervision', binary='sv',
                        family='supervision_coverflow', label='Supervision', extensions={'.sv', '.bin'}),
    'ATARI2600': dict(short='Atari2600', namespace='atclab', platform='2600', binary='2600',
                      family='atari_coverflow', label='Atari 2600', extensions={'.a26', '.bin'}),
    'ATARI7800': dict(short='Atari7800', namespace='avclab', platform='7800', binary='7800',
                      family='atari_coverflow', label='Atari 7800', extensions={'.a78', '.a26', '.bin'}),
    'ARDUBOY': dict(short='Arduboy', namespace='ardlab', platform='arduboy', binary='ard',
                    family='arduboy_coverflow', label='Arduboy', extensions={'.hex'}),
    'POKEMINI': dict(short='PokemonMini', namespace='pmclab', platform='poke_mini', binary='poke_mini',
                     family='pokemonmini_coverflow', label='Pokémon Mini（预览）', extensions={'.min'}),
    'CPS1': dict(short='CPS1', namespace='cp1lab', platform='jtcps1', binary='jtcps1', extra_platforms=['jtpatreon'],
                family='cps1_coverflow', label='CPS1', extensions={'.json'}),
    'CPS15': dict(short='CPS15', namespace='c15lab', platform='jtcps15', binary='jtcps15', extra_platforms=['jtpatreon'],
                 family='cps1_coverflow', label='CPS1.5 / QSound', extensions={'.json'}),
    'NEOGEO': dict(short='NeoGeo', namespace='ngclab', platform='ng', binary='neogeo',
                  family='neogeo_coverflow', label='Neo Geo 街机（预览）', extensions={'.json'}),
}
CPS_SYSTEMS = frozenset(('CPS1', 'CPS15'))
INSTANCE_SYSTEMS = CPS_SYSTEMS | {'NEOGEO'}
FIRMWARE = {'7800bios.bin', 'supercharger.bin', 'highscor.rom', 'hsc.a78', 'bupchip.bin'}
REGISTRY = Path(__file__).resolve().parents[1]/'tools/additional_candidates.json'


def registered(package, system):
    import delivery
    from apf_metadata import check_core, check_candidate_bitstream
    package = Path(package)
    info = PROFILES[system]
    root = package/'core'
    prefix = 'Cores/pocketlab.'+info['short']+'/'
    core = check_core(root/prefix)
    receipt = delivery.read(package/'build-receipt.json')
    digest = check_candidate_bitstream(root/prefix/(info['binary']+'.rbf_r'))
    approved = delivery.read(REGISTRY).get(system, {}).get(digest)
    if not approved or delivery.sha(package/'build-receipt.json') != approved['receipt_sha256']:
        raise ValueError('Additional core lacks a reviewed build receipt: '+system)
    if (receipt['core'] != 'pocketlab.'+info['short'] or receipt['namespace'] != info['namespace']
            or receipt['menu_format'] != 'GBAF2/'+info['platform'] or receipt['bitstream_sha256'] != digest
            or receipt['version'] != core['metadata']['version'] or receipt['minimum_slack_ns'] < 0
            or receipt['timing_records'] < 40
            or core['metadata']['platform_ids'] != [info['namespace'], info['platform']]+info.get('extra_platforms', [])
            or core['cores'] != [dict(name='default', id=0, filename=info['binary']+'.rbf_r')]):
        raise ValueError('Additional core identity/timing contract differs')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    expected = {r['path'] for r in receipt['files']}
    if len(expected) != len(receipt['files']) or actual != expected:
        raise ValueError('Additional core file inventory differs')
    for row in receipt['files']:
        delivery.check_record(root, row, system)
    for relative, digest in receipt['source_inputs'].items():
        if delivery.sha(delivery.safe_path(package/'sources', relative)) != digest:
            raise ValueError('Additional core corresponding source differs: '+relative)
    return receipt


def library(card, out, system, titles=None, covers=None):
    import delivery
    info = PROFILES[system]
    with delivery.imports():
        module = delivery.module('experiments/'+info['family']+'/library.py')
        if system.startswith('ATARI') or system in CPS_SYSTEMS:
            return module.build(info['platform'], card, out, titles, covers)
        return module.build(card, out, titles, covers)


def instance_module(system):
    import delivery
    info = PROFILES[system]
    name = 'instances.py' if system in CPS_SYSTEMS else 'library.py'
    with delivery.imports():
        return delivery.module('experiments/'+info['family']+'/'+name)


def available_instances(card, system):
    module = instance_module(system)
    if system in CPS_SYSTEMS:
        return module.available_instances(card, PROFILES[system]['platform'])
    return module.available_instances(card)


def instance_plan(card, path, system):
    module = instance_module(system)
    if system not in CPS_SYSTEMS:
        raise ValueError('This platform uses a multi-slot instance contract')
    return module.plan(card, path, PROFILES[system]['platform'])


def stage(card, package, library_root, system):
    import delivery
    import menu_bindings
    from install import refresh_library_plan
    if library_root is None:
        raise ValueError('Generate a matching filename library first')
    card, package, library_root = map(Path, (card, package, library_root))
    info = PROFILES[system]
    namespace, platform = info['namespace'], info['platform']
    core_prefix = 'Cores/pocketlab.'+info['short']+'/'
    build = registered(package, system)
    lib = delivery.read(library_root/'library-manifest.json')
    if lib['format'] != build['menu_format']:
        raise ValueError('Additional menu format differs from its core')
    menu_bindings.validate(library_root, lib, system, 'GBAF2')
    refs = lib['source_refs']
    for ref in refs:
        if not ref['path'].startswith(f'Assets/{platform}/common/'):
            raise ValueError('Additional ROM escapes the declared platform')
        delivery.check_record(card, ref)
    guards = []
    bios_files = {}
    for reference in ([] if system == 'NEOGEO' else lib.get('bios_refs', [])):
        filename = Path(reference['destination']).name
        size = lib.get('required_bios', {}).get(filename)
        if (system != 'WS' or filename not in ('bw.rom','color.rom') or reference['bytes'] != size
                or reference['destination'] != f'Assets/{namespace}/common/{filename}'
                or reference['path'] not in (f'Assets/{namespace}/common/{filename}', f'Assets/{platform}/common/{filename}')):
            raise ValueError('Unexpected BIOS source/destination')
        delivery.check_record(card, reference)
        staged = delivery.safe_path(library_root, reference['destination'])
        if staged.stat().st_size != size or delivery.sha(staged) != reference['sha256']:
            raise ValueError('Staged BIOS differs from the user-provided source')
        bios_files[reference['destination']] = reference['sha256']
        guards.append({k:reference[k] for k in ('path','bytes','sha256')})
    if system != 'NEOGEO' and len(bios_files) != len(lib.get('required_bios', {})):
        raise ValueError('Required BIOS references are incomplete')
    seeds = {r['path']: r for r in lib['files'] if r['path'].startswith('Saves/')}
    sizes = {f'Saves/{namespace}/common/{r["sha256"][:20]}.sav': r['save_bytes']
             for r in refs if r.get('save_bytes', 0)}
    cps_save_id = None
    if system in CPS_SYSTEMS:
        cps = instance_module(system)
        cps_save_id = cps.save_id
        sizes = {}
        expected_save_refs = {}
        by_path = {ref['path']: ref for ref in refs}
        for row in lib['instances']:
            instance = instance_plan(card, row['path'], system)
            rom = instance['rom']
            delivery.check_record(card, row)
            expected = {key: rom[key] for key in ('path', 'bytes', 'sha256')}
            actual = by_path.get(rom['path'], {})
            if (row['rom_path'] != rom['path'] or any(actual.get(k) != v for k,v in expected.items())
                    or any(row[key] != instance[key] for key in ('core_mode', 'button_map', 'dip_switches'))
                    or row['save_tag'] != Path(instance['nvram']['candidate_path']).stem):
                raise ValueError('CPS instance changed since library generation')
            size = instance['nvram']['bytes']
            if size not in (0, 128):
                raise ValueError('Unexpected native CPS NVRAM size')
            if size:
                destination = instance['nvram']['candidate_path']
                sizes[destination] = size
                candidate = delivery.allowed(card, destination, system)
                original = delivery.safe_path(card, instance['nvram']['original_path'])
                origin = candidate if candidate.exists() else original
                if origin.exists():
                    if not origin.is_file() or origin.stat().st_size != size:
                        raise ValueError('Native CPS save has an unexpected size')
                    record = delivery.snapshot(origin, origin.relative_to(card).as_posix())
                    expected_save_refs[record['path']] = record
                    seed_digest = record['sha256']
                else:
                    import hashlib
                    seed_digest = hashlib.sha256(b'\xff'*size).hexdigest()
                if not candidate.exists() and seeds.get(destination, {}).get('sha256') != seed_digest:
                    raise ValueError('CPS seed differs from its native instance save')
            guards.append({key: row[key] for key in ('path', 'bytes', 'sha256')})
        actual_save_refs = {row['path']: row for row in lib.get('save_refs', [])}
        if (len(actual_save_refs) != len(lib.get('save_refs', [])) or actual_save_refs != expected_save_refs):
            raise ValueError('CPS source progress changed since library generation')
        guards.extend(expected_save_refs.values())
    elif system == 'NEOGEO':
        validated = instance_module(system).validate_manifest(card, lib)
        guards.extend(validated['guards'])
        sizes = validated['save_paths']
        bios_files.update(validated['bios_files'])
    if seeds.keys() - sizes.keys():
        raise ValueError('Unexpected additional save seed')
    for relative, size in sizes.items():
        existing = delivery.allowed(card, relative, system)
        if existing.exists():
            if not existing.is_file() or existing.stat().st_size != size:
                raise ValueError('Existing progress has an unexpected size: '+relative)
            guards.append(delivery.snapshot(existing, relative))
        elif relative not in seeds or seeds[relative]['bytes'] != size:
            raise ValueError('Missing isolated save seed: '+relative)
    installed = delivery.safe_path(card, core_prefix+'core.json').is_file()
    changes = []
    for root, manifest in ((package/'core', build), (library_root, lib)):
        for row in manifest['files']:
            relative = row['path']
            delivery.check_record(root, row, system)
            target = delivery.allowed(card, relative, system)
            if relative in sizes and target.is_file():
                continue
            if relative in bios_files and target.is_file():
                if delivery.sha(target) != bios_files[relative]:
                    raise ValueError('Existing BIOS would be replaced: '+relative)
                guards.append(delivery.snapshot(target, relative))
                continue
            if target.exists() and not installed:
                raise ValueError('First addition requires an unused menu destination: '+relative)
            changes.append({**row, 'source': str(root)})
    result = {'identity': delivery.identity(card), 'changes': changes, 'source_refs': refs,
              'operation': 'first_addition', 'guards': guards}
    if installed:
        # Until a future release adds an explicit migration, refresh only the
        # same reviewed bitstream and retain every user's JSON setting.
        binary = info['binary']+'.rbf_r'
        if delivery.sha(card/core_prefix/binary) != delivery.sha(package/'core'/core_prefix/binary):
            raise ValueError('An explicit reviewed core upgrade is required')
        existing = menu_bindings.existing(card, system, refs=refs, cps_save_id=cps_save_id)
        result.update(refresh_library_plan(card, package/'core', changes, core_prefix))
        result['guards'].extend(guards+existing)
    result['summary'] = {key: lib[key] for key in ('pages', 'game_refs', 'cover_hits', 'fallback_covers', 'excluded')}
    result['summary']['operation'] = result['operation']
    return result
