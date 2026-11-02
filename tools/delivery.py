#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare one card-bound native-menu update; apply only after complete preflight."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

from build_library import sha
from install import identity, publish, safe_path
from apf_metadata import check_candidate_bitstream

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {'GB-GBC': ('CoverFlow', 'gbclab', 'gbc'), 'GBA': ('GBA', 'gbalab', 'gba'),
            'NES': ('NES', 'neslab', 'nes'), 'GG': ('GG', 'ggclab', 'gg'),
            'SMS': ('SMS', 'smslab', 'sms'), 'SG1000': ('SG1000', 'sgclab', 'sg1000')}
FORMAT = 'POCKET-DELIVERY-2'
LEGACY_FORMAT = 'POCKET-DELIVERY-1'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf8') as out:
        out.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)


def separate(a, b):
    if a.is_relative_to(b) or b.is_relative_to(a):
        raise ValueError('Card, inputs, staging and backup must be separate directories')


def allowed(root, rel, component):
    short, ns, binary = PROFILES[component]
    core = 'Cores/pocketlab.' + short + '/'
    assets = 'Assets/' + ns + '/common/'
    names = ['core.json', 'data.json', 'audio.json', 'input.json', 'interact.json',
             'video.json', 'variants.json', binary + '.rbf_r']
    if component == 'GB-GBC':
        names += ['icon.bin', 'info.txt']
    leaf = 'covers.bin' if component == 'GB-GBC' else 'menu.bin'
    valid = rel in {core + n for n in names} | {
        f'Platforms/{ns}.json', f'Platforms/_images/{ns}.bin', assets + leaf}
    valid |= bool(re.fullmatch(re.escape(assets) + r'libs/[0-9a-f]{16}\.bin', rel))
    if component == 'GB-GBC':
        valid |= rel == assets + 'gbc_bios.bin'
    if component in ('NES', 'GG', 'SMS', 'SG1000'):
        valid |= bool(re.fullmatch(rf'Saves/{ns}/common/[0-9a-f]{{20}}\.sav', rel))
    if component in ('GG', 'SMS', 'SG1000'):
        valid |= bool(re.fullmatch(rf'Assets/{ns}/cheat/[0-9a-f]{{20}}\.cht', rel))
    if not valid:
        raise ValueError('Outside native-menu delivery scope: ' + rel)
    return safe_path(root, rel)


def digest(path):
    if path.exists() and not path.is_file():
        raise ValueError('Expected a file: ' + str(path))
    return sha(path) if path.is_file() else None


def check_record(root, row, component=None):
    path = allowed(root, row['path'], component) if component else safe_path(root, row['path'])
    if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
        raise ValueError('File identity changed: ' + row['path'])


def snapshot(path, rel):
    return {'path': rel, 'bytes': path.stat().st_size, 'sha256': sha(path)}


def save_directories(components):
    components = set(components)
    paths = {'Saves/' + PROFILES[name][1] + '/common' for name in components}
    if 'GB-GBC' in components:
        paths.update(('Saves/gbclab/common/meta', 'Saves/gbclab/common/folders'))
    return sorted(paths)


def checked_directories(card, result):
    if result['format'] == LEGACY_FORMAT:
        if 'directories' in result:
            raise ValueError('Legacy plans cannot declare save directories')
        paths = save_directories(['GB-GBC']) if 'GB-GBC' in result['components'] else []
    else:
        paths = save_directories(result['components'])
        if result.get('directories') != paths:
            raise ValueError('Save-directory plan differs from the selected native components')
    for relative in paths:
        path = safe_path(card, relative)
        if path.exists() and not path.is_dir():
            raise ValueError('Expected ordinary-save directory: ' + relative)
    return paths


@contextmanager
def imports():
    """Existing experimental tools have sibling imports; keep them local."""
    previous = sys.path[:]
    old_controller = sys.modules.pop('controller', None)
    sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'experiments/sega_coverflow')]
    try:
        yield
    finally:
        sys.path[:] = previous
        sys.modules.pop('controller', None)
        if old_controller is not None:
            sys.modules['controller'] = old_controller


def module(relative):
    spec = importlib.util.spec_from_file_location('delivery_' + relative.replace('/', '_').replace('.', '_'), ROOT/relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def append_styles(video, platform):
    """Offer supported styles without replacing defaults or existing scaler IDs."""
    from display_styles import MODES
    modes = video['video'].setdefault('display_modes', [])
    ids = {int(row['id'], 0) if isinstance(row['id'], str) else row['id'] for row in modes}
    modes.extend({'id': value} for value in MODES[platform] if int(value, 0) not in ids)
    return video


def gb_stage(card, package, out, mapping):
    """Preserve the actual accepted entry, its icons, scalers and user metadata."""
    from build_release import RBF_SHA
    import install
    import update_display
    from style_library import decode
    old = card/'Cores/pocketlab.CoverFlow'
    candidate = read(package/'core/release-manifest.json')
    if sha(old/'gbc.rbf_r') != RBF_SHA or candidate['bitstream_sha256'] != RBF_SHA:
        raise ValueError('GB/GBC update requires the retained accepted bitstream')
    install.read_manifest(package/'core', 'release-manifest.json')
    staged = out/'library'
    lib = update_display.stage(card, staged, mapping)
    # Check the actual reachable ROM bytes, including pages whose artwork is unchanged.
    refs = {}
    for row in lib['source_packs']:
        for entry in decode(safe_path(card, row['path']).read_bytes())['entries']:
            if not entry['record'][40] & 128:
                rel = entry['paths'][0].lstrip('/')
                refs[rel] = snapshot(safe_path(card, rel), rel)
    lib['source_refs'] = list(refs.values())
    write(staged/'library-manifest.json', lib)
    derived = out/'package'
    records, guards = [], []
    for row in candidate['files']:
        rel = row['path']
        source, target = allowed(card, rel, 'GB-GBC'), allowed(derived, rel, 'GB-GBC')
        guards.append(snapshot(source, rel))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if rel.endswith('/core.json'):
            metadata = read(target)
            metadata['core']['metadata'].update(version=candidate['version'], date_release='2026-11-02')
            write(target, metadata)
        if rel.endswith('/video.json'):
            write(target, append_styles(read(target), 'gbc'))
        records.append(snapshot(target, rel))
    write(derived/'release-manifest.json', {**candidate, 'files': records})
    result = install.plan(card, derived, staged)
    result['source_refs'] = lib['source_refs']
    result['guards'] = guards + [snapshot(safe_path(card, r['path']), r['path']) for r in lib['source_packs']]
    result['summary'] = {k: lib[k] for k in ('updated_games', 'unique_games', 'reachable_pages', 'unmatched_mapping')}
    return result


def gb_filename_plan(card, package, library, installed):
    from build_release import RBF_SHA
    import install
    import menu_bindings
    if library is None:
        raise ValueError('GB/GBC first install requires a filename-built library and your own BIOS')
    release = read(package/'core/release-manifest.json')
    if release['bitstream_sha256'] != RBF_SHA or sha(package/'core/Cores/pocketlab.CoverFlow/gbc.rbf_r') != RBF_SHA:
        raise ValueError('Filename menus require the retained accepted GB/GBC bitstream')
    lib = read(library/'library-manifest.json')
    if lib.get('format') != 9:
        raise ValueError('Filename menus require a v9 GB/GBC library')
    result = install.plan(card, package/'core', library)
    menu_bindings.validate(library, lib, 'GB-GBC')
    bios = 'Assets/gbclab/common/gbc_bios.bin'
    guards = []
    if installed:
        if sha(safe_path(card, bios)) != sha(safe_path(library, bios)):
            raise ValueError('Library refresh requires the existing GBC BIOS')
        guards = menu_bindings.existing(card, 'GB-GBC', refs=lib['source_refs'])
        result.update(install.refresh_library_plan(card, package/'core', result['changes'], 'Cores/pocketlab.CoverFlow/'))
    else:
        for row in release['files'] + lib['files']:
            path = safe_path(card, row['path'])
            if not path.exists():
                continue
            if row['path'] != bios or not path.is_file() or sha(path) != row['sha256']:
                raise ValueError('First GB/GBC install refuses an existing destination: ' + row['path'])
            guards.append(snapshot(path, row['path']))
        result['operation'] = 'first_addition'
    result['source_refs'] = lib['source_refs']
    result['guards'] = result.get('guards', []) + guards
    result['summary'] = {'operation': result['operation'], 'pages': lib['pack_count'],
                         'unique_games': len({r['sha256'] for r in lib['source_refs']}), 'warnings': lib.get('warnings', [])}
    return result


def component_plan(card, config, base, out):
    name = config['id']
    def path(key):
        return (base/config[key]).resolve() if config.get(key) else None
    package = path('package')
    if package is None:
        raise ValueError('Each component requires a package')
    for key in ('package', 'library', 'mapping', 'titles', 'covers', 'folders', 'cheats'):
        if path(key) is not None:
            separate(path(key), card)
            separate(path(key), out)
    with imports():
        if name == 'GB-GBC':
            installed = safe_path(card, 'Cores/pocketlab.CoverFlow/core.json').is_file()
            if path('library') or not installed:
                if path('mapping'):
                    raise ValueError('Choose a GB/GBC filename library or an existing-menu display mapping')
                return gb_filename_plan(card, package, path('library'), installed)
            mapping = read(path('mapping')) if path('mapping') else {}
            # Artwork paths in portable configurations are relative to that mapping file.
            for patch in mapping.values():
                if patch.get('cover'):
                    patch['cover'] = str((path('mapping').parent/patch['cover']).resolve())
            return gb_stage(card, package, out, mapping)
        if name == 'GBA':
            library = path('library')
            if library is None:
                raise ValueError('GBA requires a matching library')
            installed = safe_path(card, 'Cores/pocketlab.GBA/core.json').is_file()
            refresh = False
            if installed:
                with safe_path(card, 'Assets/gbalab/common/menu.bin').open('rb') as source:
                    f2 = source.read(8) == b'GBAF\x02\0\0\0'
                refresh = f2 and sha(safe_path(card, 'Cores/pocketlab.GBA/gba.rbf_r')) == sha(package/'core/Cores/pocketlab.GBA/gba.rbf_r')
            if not installed or refresh:
                installer = module('experiments/gba_menu/install.py')
                result = installer.plan(card, package, library, refresh=refresh)
                result['summary'] = {k: result[k] for k in ('roms', 'pages', 'core_version', 'operation')}
                return result
            update = module('experiments/gba_coverflow/update.py')
            staging = out/'update'
            result = update.stage(card, package, library, staging)
            video = staging/'Cores/pocketlab.GBA/video.json'
            write(video, append_styles(read(video), 'gba'))
            # Recompute after the append-only optional display registration.
            rel = 'Cores/pocketlab.GBA/video.json'
            result['changes'] = [r for r in result['changes'] if r['path'] != rel]
            if sha(video) != sha(safe_path(card, rel)):
                result['changes'].append({**snapshot(video, rel), 'previous_sha256': sha(safe_path(card, rel))})
            for row in result['changes']:
                row['source'] = str(staging)
            result['source_refs'] = result['roms']
            result['guards'] = [snapshot(p, p.relative_to(card).as_posix()) for p in
                                (card/'Cores/pocketlab.GBA').iterdir() if p.is_file()]
            result['summary'] = {k: result[k] for k in ('roms_verified', 'pages_checked', 'core_version')}
            result['summary']['operation'] = 'format_upgrade'
            return result
        folder = 'nes_coverflow' if name == 'NES' else 'sega_coverflow'
        library = module(f'experiments/{folder}/library.py')
        installer = module(f'experiments/{folder}/install.py')
        staged = path('library') or out/'library'
        kwargs = {key: path(key) for key in ('titles', 'covers', 'folders')}
        platform = PROFILES[name][2]
        if name != 'NES':
            kwargs.update(platform=platform, cheats=path('cheats'))
        manifest = read(staged/'library-manifest.json') if path('library') else library.build(card, staged, **kwargs)
        args = (card, package, staged) + (() if name == 'NES' else (platform,))
        installed = safe_path(card, 'Cores/pocketlab.'+PROFILES[name][0]+'/core.json').is_file()
        result = installer.plan(*args, refresh=installed)
        result['summary'] = {key: manifest[key] for key in ('unique_games', 'pages', 'covers', 'excluded', 'warnings')}
        result['summary']['cheat_matched_versions'] = len(manifest.get('cheats', []))
        result['summary']['operation'] = result.get('operation', 'first_addition')
        return result


def seal(card, out, parts):
    """All component validators finish before an installable plan is published."""
    ident = identity(card)
    changes, refs, guards, seen = [], {}, {}, set()
    for name, part in parts:
        if part['identity'] != ident:
            raise ValueError('Component belongs to a different card')
        platform = PROFILES[name][2]
        for row in part.get('source_refs', []):
            if not row['path'].startswith(tuple(f'Assets/{p}/common/' for p in (('gb', 'gbc') if name == 'GB-GBC' else (platform,)))):
                raise ValueError('Foreign ROM reference')
            check_record(card, row)
            if row['path'] in refs and refs[row['path']] != row:
                raise ValueError('Conflicting ROM identities')
            refs[row['path']] = row
        for row in part.get('guards', []):
            check_record(card, row)
            guards[row['path']] = row
        for row in part['changes']:
            rel = row['path']
            if rel.casefold() in seen:
                raise ValueError('Components overlap: ' + rel)
            seen.add(rel.casefold())
            target = allowed(card, rel, name)
            previous = digest(target)
            if previous != row.get('previous_sha256'):
                raise ValueError('Destination changed during preflight: ' + rel)
            if rel.startswith('Saves/') and previous is not None:
                raise ValueError('Existing progress must never be staged or overwritten')
            source = allowed(Path(row['source']), rel, name)
            check_record(Path(row['source']), row, name)
            if rel.endswith('.rbf_r'):
                check_candidate_bitstream(source)
            dest = allowed(out/'payload', rel, name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            check_record(out/'payload', row, name)
            changes.append({**{key: row[key] for key in ('path', 'bytes', 'sha256')}, 'component': name, 'previous_sha256': previous})
    # New data and pages precede binaries; core/platform entry metadata is last.
    changes.sort(key=lambda c: (c['path'].startswith('Platforms/'), c['path'].endswith('/core.json'), c['path'].endswith('.rbf_r'), c['path']))
    result = {'format': FORMAT, 'identity': ident, 'changes': changes, 'source_refs': list(refs.values()),
              'directories': save_directories(name for name, _ in parts),
              'guards': list(guards.values()), 'components': {name: part.get('summary', {}) for name, part in parts},
              'status': 'prepared_only', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'firmware_writes': 0, 'original_save_writes': 0, 'hardware_acceptance': 'pending'}
    checked_directories(card, result)
    write(out/'delivery-plan.json', result)
    return result


def prepare(card, config, out):
    card, config, out = map(lambda p: Path(p).resolve(), (card, config, out))
    identity(card)
    separate(card, out)
    separate(config.parent, card)
    separate(config.parent, out)
    if out.exists():
        raise ValueError('Use a fresh local staging directory')
    settings = read(config)
    names = [row['id'] for row in settings['components']]
    if not names or len(set(names)) != len(names) or any(name not in PROFILES for name in names):
        raise ValueError('Expected unique supported native components')
    out.mkdir(parents=True)
    parts = [(row['id'], component_plan(card, row, config.parent, out/'components'/row['id'])) for row in settings['components']]
    result = seal(card, out, parts)
    return result


def load_plan(card, staging):
    result = read(staging/'delivery-plan.json')
    if result['format'] not in (FORMAT, LEGACY_FORMAT) or identity(card) != result['identity']:
        raise ValueError('Different card or unsupported plan')
    checked_directories(card, result)
    seen = set()
    for row in result['changes']:
        rel, component = row['path'], row['component']
        if component not in result['components'] or rel.casefold() in seen:
            raise ValueError('Invalid or duplicate component path')
        seen.add(rel.casefold())
        target = allowed(card, rel, component)
        if rel.startswith('Saves/') and row['previous_sha256'] is not None:
            raise ValueError('Existing saves cannot be overwritten')
        if digest(target) != row['previous_sha256']:
            raise ValueError('Destination changed after preparation: ' + rel)
        check_record(staging/'payload', row, component)
        if rel.endswith('.rbf_r'):
            check_candidate_bitstream(allowed(staging/'payload', rel, component))
    for row in result['guards'] + result['source_refs']:
        check_record(card, row)
    return result


def protected_progress(card, components):
    roots = {'gba', 'gbalab'}  # Always protect the important existing GBA progress.
    for name in components:
        roots.update(PROFILES[name][1:])
        if name == 'GB-GBC':
            roots.update(('gb', 'gbc'))
    records = []
    for name in sorted(roots):
        root = safe_path(card, 'Saves/' + name)
        for path in sorted(root.rglob('*')):
            rel = path.relative_to(card).as_posix()
            safe_path(card, rel)
            if path.is_file():
                records.append(snapshot(path, rel))
    return records


def apply(card, staging, backup):
    card, staging, backup = map(lambda p: Path(p).resolve(), (card, staging, backup))
    for a, b in ((card, staging), (card, backup), (staging, backup)):
        separate(a, b)
    if backup.exists():
        raise ValueError('Use a new external backup directory')
    result = load_plan(card, staging)
    protected = protected_progress(card, result['components'])
    needed = sum(row['bytes'] for row in protected) + sum(allowed(card, c['path'], c['component']).stat().st_size
                 for c in result['changes'] if c['previous_sha256'] is not None)
    ancestor = backup.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < needed + 32*1024**2 or shutil.disk_usage(card).free < sum(c['bytes'] for c in result['changes']) + 32*1024**2:
        raise ValueError('Insufficient space for verified backup and atomic publication')
    backup.mkdir(parents=True)
    for row in protected:
        dest = safe_path(backup/'progress', row['path'])
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(safe_path(card, row['path']), dest)
        check_record(backup/'progress', row)
    for row in result['changes']:
        if row['previous_sha256'] is not None:
            source = allowed(card, row['path'], row['component'])
            dest = allowed(backup/'previous', row['path'], row['component'])
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            if sha(dest) != row['previous_sha256']:
                raise ValueError('Original file backup mismatch')
    result.update(status='backed_up_before_writes', protected_progress=protected)
    receipt = backup/'delivery-receipt.json'
    write(receipt, result)
    load_plan(card, staging)
    for row in protected:
        check_record(card, row)
    try:
        for relative in checked_directories(card, result):
            if identity(card) != result['identity']:
                raise ValueError('Card identity changed during directory creation')
            safe_path(card, relative).mkdir(parents=True, exist_ok=True)
        with (backup/'journal.jsonl').open('x', encoding='utf8') as journal:
            for row in result['changes']:
                if identity(card) != result['identity']:
                    raise ValueError('Card identity changed during publication')
                target = allowed(card, row['path'], row['component'])
                if digest(target) != row['previous_sha256']:
                    raise ValueError('Destination changed during publication')
                journal.write(json.dumps({'intent': row['path'], 'sha256': row['sha256']}) + '\n')
                journal.flush()
                os.fsync(journal.fileno())
                publish(allowed(staging/'payload', row['path'], row['component']), target, row['sha256'])
        for row in protected:
            check_record(card, row)
    except (OSError, ValueError) as error:
        result.update(status='interrupted', error=str(error))
        write(receipt, result)
        try:
            rollback(card, backup, execute=True)
            result['status'] = 'interrupted_menu_files_restored_saves_retained'
        except (OSError, ValueError) as restore_error:
            result['rollback_error'] = str(restore_error)
        write(receipt, result)
        raise
    result['status'] = 'installed_sha256_verified_hardware_pending'
    write(receipt, result)
    return result


def rollback(card, backup, execute=False):
    card, backup = Path(card).resolve(), Path(backup).resolve()
    separate(card, backup)
    result = read(backup/'delivery-receipt.json')
    if result['format'] not in (FORMAT, LEGACY_FORMAT) or identity(card) != result['identity']:
        raise ValueError('Rollback card identity differs')
    changes = []
    for row in result['changes']:
        target = allowed(card, row['path'], row['component'])
        if row['path'].startswith('Saves/'):
            continue  # Includes seed files that may now contain real progress.
        actual = digest(target)
        if actual == row['previous_sha256']:
            continue
        if actual != row['sha256']:
            raise ValueError('Changed file; preserve it for review: ' + row['path'])
        if row['previous_sha256'] is not None and sha(allowed(backup/'previous', row['path'], row['component'])) != row['previous_sha256']:
            raise ValueError('Rollback backup identity differs')
        if row['previous_sha256'] is not None and row['path'].endswith('.rbf_r'):
            check_candidate_bitstream(allowed(backup/'previous', row['path'], row['component']))
        changes.append(row)
    if execute:
        for row in reversed(changes):
            target = allowed(card, row['path'], row['component'])
            if identity(card) != result['identity'] or sha(target) != row['sha256']:
                raise ValueError('Card changed during rollback')
            if row['previous_sha256'] is None:
                target.unlink()
            else:
                publish(allowed(backup/'previous', row['path'], row['component']), target, row['previous_sha256'])
        result['status'] = 'menu_files_restored_saves_retained'
        write(backup/'delivery-receipt.json', result)
    return {'applied': execute, 'menu_files_restored': len(changes), 'save_writes': 0, 'firmware_writes': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'verify', 'apply', 'rollback'))
    parser.add_argument('--card', required=True)
    for key in ('config', 'staging', 'backup'):
        parser.add_argument('--' + key)
    parser.add_argument('--execute', action='store_true', help='Execute rollback; default is preview')
    args = parser.parse_args()
    if args.action == 'prepare' and not (args.config and args.staging):
        parser.error('prepare requires --config and new --staging')
    if args.action in ('verify', 'apply') and not args.staging:
        parser.error('verify/apply requires --staging')
    if args.action in ('apply', 'rollback') and not args.backup:
        parser.error('apply/rollback requires --backup')
    try:
        card = Path(args.card).resolve()
        if args.action == 'prepare':
            result = prepare(card, args.config, args.staging)
        elif args.action == 'verify':
            result = load_plan(card, Path(args.staging).resolve())
        elif args.action == 'apply':
            result = apply(card, args.staging, args.backup)
        else:
            result = rollback(card, args.backup, args.execute)
        print(json.dumps({k: v for k, v in result.items() if k not in ('changes', 'guards', 'source_refs', 'protected_progress', 'identity', 'components')}, ensure_ascii=True, indent=2))
        if 'changes' in result:
            print('Menu/seed files: %d; existing save/ROM/firmware writes: 0' % len(result['changes']))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()
