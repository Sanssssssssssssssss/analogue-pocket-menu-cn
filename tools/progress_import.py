#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Import ordinary progress by ROM identity, before a delivery plan is sealed."""
import hashlib
import re
from datetime import datetime
from pathlib import Path, PurePosixPath

import build_menus
import delivery

NATIVE_IMPORT_PENDING = frozenset(('WS', 'ARDUBOY', 'POKEMINI', 'CPS1', 'CPS15'))


class Conflict(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__('Ordinary-save sources need an explicit selection; see save-import-report.json')


def gb_layout(path):
    with path.open('rb') as stream:
        header = stream.read(0x150)
    if len(header) < 0x150:
        raise ValueError('Incomplete Game Boy cartridge header')
    mapper, ram = header[0x147], header[0x149]
    # Specialized EEPROM/camera layouts are not guessed from an extension.
    if mapper not in (0, 1, 2, 3, 5, 6, 8, 9, 0x0f, 0x10, 0x11, 0x12, 0x13,
                      0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e):
        raise ValueError('This GB mapper requires a dedicated progress converter')
    battery = mapper in (3, 6, 9, 0x0f, 0x10, 0x13, 0x1b, 0x1e)
    sizes = {0: 0, 1: 2048, 2: 8192, 3: 32768, 4: 131072, 5: 65536}
    if ram not in sizes:
        raise ValueError('Unknown GB RAM-size header')
    size = (512 if mapper == 6 else sizes[ram]) if battery else 0
    return size, mapper in (0x0f, 0x10)


def targets(card, components, base):
    """Only records already validated by component_plan enter the install transaction."""
    result = []
    for component in components:
        system = component['id']
        if not component.get('library'):
            continue
        library = (base/component['library']).resolve()
        manifest = delivery.read(library/'library-manifest.json')
        ns = delivery.PROFILES[system][1]
        refs = manifest['roms' if system == 'GBA' else 'source_refs']
        for ref in refs:
            delivery.check_record(card, ref)
            size, rtc = 0, False
            if system == 'GB-GBC':
                try:
                    size, rtc = gb_layout(delivery.safe_path(card, ref['path']))
                except ValueError as exc:
                    result.append({'system': system, 'rom': ref, 'unsupported': str(exc)})
                    continue
            elif system == 'GBA':
                size = ref['save_bytes']
            else:
                size = ref.get('save_bytes', {'NES': 262144, 'GG': 32768, 'SMS': 32768,
                               'SG1000': 32768}.get(system, delivery.CONSOLE_SAVES.get(system, (0,))[0]))
            if system == 'CPS2' or system in delivery.additional_menus.CPS_SYSTEMS:
                if system == 'CPS2':
                    with delivery.imports():
                        cps = delivery.module('experiments/console_coverflow/cps2.py')
                for instance in manifest['instances']:
                    if instance['rom_path'] != ref['path']:
                        continue
                    checked = (cps.plan(card, instance['path']) if system == 'CPS2'
                               else delivery.additional_menus.instance_plan(card, instance['path'], system))
                    if checked['nvram']['bytes']:
                        target = {'system': system, 'rom': ref, 'size': checked['nvram']['bytes'], 'rtc': False,
                                  'path': checked['nvram']['candidate_path'], 'instance': instance}
                        if system in delivery.additional_menus.CPS_SYSTEMS:
                            target['native_instance_seed'] = checked['nvram']['original_path']
                        result.append(target)
            elif size or rtc:
                result.append({'system': system, 'rom': ref, 'size': size, 'rtc': rtc,
                               'path': f'Saves/{ns}/common/{ref["sha256"][:20]}.sav'})
    # Identical cartridges can occur in several collections. Inspect all origins once.
    unique = {}
    for row in result:
        key = row.get('path', row['rom']['path'])
        if key in unique:
            unique[key]['rom_paths'].append(row['rom']['path'])
        else:
            unique[key] = {**row, 'rom_paths': [row['rom']['path']]}
    return list(unique.values())


def native_save_paths(relative):
    path = PurePosixPath(relative)
    platform = path.parts[1]
    inner = PurePosixPath(*path.parts[3:])
    stem = PurePosixPath('Saves')/platform/'common'/inner
    extensions = ('.sav', '.srm') if platform in ('gb', 'gbc', 'gba') else ('.sav',)
    return [rel for ext in extensions for rel in (stem.with_suffix(ext).as_posix(), stem.as_posix()+ext)]


def convert(raw, target, source_format, rtc=None):
    system, size = target['system'], target['size']
    if system in NATIVE_IMPORT_PENDING:
        raise ValueError('This native save layout needs a verified converter; equal length is insufficient')
    if source_format == 'raw-handheld' and system not in ('GB-GBC', 'GBA'):
        raise ValueError('Raw handheld import is only defined for GB/GBC and GBA')
    if system == 'GB-GBC':
        expected = size + (16 if target['rtc'] and source_format == 'pocket-native' else 0)
        if len(raw) != expected:
            raise ValueError('GB save size/RTC layout differs from the selected source format')
        if rtc is not None:
            raise ValueError('Separate GB RTC formats require a dedicated converter')
        return raw, None, 'native GB body/RTC' if source_format == 'pocket-native' else 'raw GB SRAM; RTC not converted'
    if system == 'GBA':
        if source_format == 'pocket-native' and len(raw) in (65552, 131088):
            if rtc is not None and rtc != raw[-16:]:
                raise ValueError('Embedded and separate GBA RTC disagree')
            raw, rtc = raw[:-16], raw[-16:]
        if rtc is not None and (source_format != 'pocket-native' or len(rtc) != 16):
            raise ValueError('Only the native 16-byte GBA RTC format can be migrated')
        if rtc is not None:
            validate_gba_rtc(rtc)
        if len(raw) not in (512, 8192, 32768, 65536, 131072) or len(raw) > size:
            raise ValueError('GBA save size cannot be safely converted')
        return raw.ljust(size, b'\xff'), rtc, 'raw GBA body, FF padding only; never truncate'
    if source_format != 'pocket-native' or len(raw) != size:
        raise ValueError('Native save layout/size differs; no guessed conversion')
    return raw, None, 'byte-identical native ordinary save'


def validate_gba_rtc(raw):
    """Mirror the .9 RTC loader's packed-BCD validity contract, not an emulator format."""
    if len(raw) != 16 or int.from_bytes(raw[:4], 'little') in (0, 0xffffffff):
        raise ValueError('Native GBA RTC timestamp is missing or invalid')
    value = int.from_bytes(raw[4:10], 'little')
    if value >> 42 or any(raw[10:]):
        raise ValueError('Native GBA RTC reserved bits are not zero')
    def bcd(shift, bits):
        field = (value >> shift) & ((1 << bits)-1)
        if field & 15 > 9:
            raise ValueError('Native GBA RTC has an invalid BCD digit')
        return (field >> 4)*10+(field & 15)
    year = bcd(34, 8)
    if year > 99 or (value >> 20) & 7 > 6:
        raise ValueError('Native GBA RTC year or weekday is invalid')
    try:
        datetime(2000+year, bcd(29, 5), bcd(23, 6), bcd(14, 6), bcd(7, 7), bcd(0, 7))
    except ValueError as exc:
        raise ValueError('Native GBA RTC calendar/time is invalid') from exc


def source_records(card, settings, selected, needed=None):
    sources = [{'root': str(card), 'format': 'pocket-native'}] if settings.get('same_card', True) else []
    sources += settings.get('sources', [])
    output = []
    seen = set()
    for specification in sources:
        root = Path(specification['root']).resolve()
        kind = specification.get('format', 'pocket-native')
        if kind not in ('pocket-native', 'raw-handheld'):
            raise ValueError('Unknown ordinary-save source format')
        identity = (str(root).casefold(), kind, specification.get('roms'), specification.get('saves'))
        if identity in seen:
            continue
        seen.add(identity)
        if kind == 'pocket-native':
            delivery.identity(root)
            active = {system for system in selected if system not in NATIVE_IMPORT_PENDING
                      and (needed is None or needed.get(system))}
            if not active:
                continue
            files = build_menus.discover(root)
            for system in active:
                if system == 'CPS2':
                    with delivery.imports():
                        cps = delivery.module('experiments/console_coverflow/cps2.py')
                    for rel in files.get(system, []):
                        try:
                            plan = cps.plan(root, rel)
                        except (OSError, ValueError, KeyError, TypeError):
                            # Unsupported instances are also excluded by the library builder.
                            continue
                        output.append({'root': root, 'format': kind, 'system': system, 'rom': plan['rom'],
                                       'saves': [plan['nvram']['original_path'], plan['nvram']['candidate_path']],
                                       'binding': Path(plan['nvram']['candidate_path']).stem,
                                       'extra': [delivery.snapshot(root/rel, rel)]})
                else:
                    ns = delivery.PROFILES[system][1]
                    if needed is None:
                        save_root = delivery.safe_path(root, f'Saves/{ns}/common')
                        has_hash_save = any(re.fullmatch(r'[0-9a-f]{20}\.sav', p.name.lower()) and p.is_file()
                                            for p in save_root.glob('*.sav'))
                    else:
                        has_hash_save = any(delivery.safe_path(root, f'Saves/{ns}/common/{digest[:20]}.sav').is_file()
                                            for digest in needed[system])
                    for rel in files.get(system, []):
                        native_paths = native_save_paths(rel)
                        # A hash-named donor still requires ROM identity even
                        # when its original filename-based save is absent.
                        if not has_hash_save and not any(delivery.safe_path(root, p).is_file() for p in native_paths):
                            continue
                        path = delivery.safe_path(root, rel)
                        record = delivery.snapshot(path, rel)
                        if needed is not None and record['sha256'] not in needed[system]:
                            continue
                        output.append({'root': root, 'format': kind, 'system': system, 'rom': record,
                                       'saves': native_paths + [f'Saves/{ns}/common/{record["sha256"][:20]}.sav'],
                                       'extra': []})
        else:
            system = specification['system']
            if system not in ('GB-GBC', 'GBA') or system not in selected:
                raise ValueError('Select a GB/GBC or GBA source library')
            roms = delivery.safe_path(root, specification['roms'])
            saves = delivery.safe_path(root, specification['saves'])
            if not roms.is_dir() or not saves.is_dir():
                raise ValueError('Explicit donor ROM and ordinary-save directories required')
            if needed is not None and not needed.get(system):
                continue
            for path in sorted(roms.rglob('*')):
                if not path.is_file() or path.suffix.lower() not in build_menus.SYSTEMS[system][1]:
                    continue
                rel = path.relative_to(root).as_posix()
                delivery.safe_path(root, rel)
                inner = path.relative_to(roms)
                candidates = [(saves/inner).with_suffix(ext) for ext in ('.sav', '.srm')]
                if not any(delivery.safe_path(root, p.relative_to(root).as_posix()).is_file() for p in candidates):
                    continue
                output.append({'root': root, 'format': kind, 'system': system,
                               'rom': delivery.snapshot(path, rel),
                               'saves': [p.relative_to(root).as_posix() for p in candidates], 'extra': []})
    return output


def collect(card, components, base, settings):
    rows = targets(card, components, base)
    needed = {}
    for row in rows:
        if 'path' in row and not delivery.safe_path(card, row['path']).exists():
            needed.setdefault(row['system'], set()).add(row['rom']['sha256'])
    sources = source_records(card, settings, {row['system'] for row in rows}, needed)
    by_rom = {}
    for source in sources:
        by_rom.setdefault((source['system'], source['rom']['sha256']), []).append(source)
    report, payloads = [], {}
    choices = settings.get('choices', {})
    for target in rows:
        public = {**target, 'candidates': [], 'errors': []}
        report.append(public)
        if 'unsupported' in target:
            public['status'] = 'unsupported_layout'
            continue
        path = delivery.safe_path(card, target['path'])
        rtc_dest = path.with_suffix('.rtc') if target['system'] == 'GBA' else None
        choice = choices.get(target['path'])
        if path.exists():
            accepted = {target['size']}
            if target['system'] == 'GB-GBC':
                # The native GB loader routes bytes beyond cartridge RAM to its
                # RTC loader, never back into RAM. Preserve an existing legacy
                # trailer even for a non-RTC mapper; new imports stay strict.
                accepted.add(target['size'] + 16)
            if not path.is_file() or path.stat().st_size not in accepted:
                raise ValueError('Existing target save has an unexpected size; preserve it for review: '+str(path))
            if (target['system'] == 'GB-GBC' and not target['rtc']
                    and path.stat().st_size == target['size'] + 16):
                public['errors'].append('Existing GB/GBC save has a 16-byte trailer although the ROM header has no RTC; '
                                        'preserving every byte without conversion: '+target['path'])
            if rtc_dest and rtc_dest.exists() and (not rtc_dest.is_file() or rtc_dest.stat().st_size != 16):
                raise ValueError('Existing target RTC is not the native 16-byte format: '+str(rtc_dest))
            if rtc_dest and rtc_dest.exists():
                try:
                    validate_gba_rtc(rtc_dest.read_bytes())
                except ValueError as exc:
                    # The native loader can fall back to the host clock. Keep the existing bytes.
                    public['errors'].append(f'{rtc_dest.relative_to(card).as_posix()}: {exc}')
            public['status'] = 'keep_existing'
            continue
        if 'native_instance_seed' in target:
            # Its family validator already checked the exact slot-to-file mapping,
            # source digest and byte-identical seed before this report is collected.
            source = delivery.safe_path(card, target['native_instance_seed'])
            public['status'] = 'prepared_native_instance' if source.is_file() else 'new_native_save'
            continue
        if target['system'] in NATIVE_IMPORT_PENDING:
            public.update(status='unsupported_layout',
                          unsupported='Native save import awaits format validation; existing menu progress is preserved')
            continue
        if rtc_dest and rtc_dest.exists():
            public.update(status='explicitly_skipped' if choice == 'skip' else 'conflict',
                          errors=['Existing RTC without the target save; automatic pairing refused'])
            continue
        seen = set()
        for source in by_rom.get((target['system'], target['rom']['sha256']), []):
            if target['system'] == 'CPS2' and source['binding'] != Path(target['path']).stem:
                continue
            for relative in source['saves']:
                root = source['root']
                origin = delivery.safe_path(root, relative)
                if not origin.is_file() or origin == path or str(origin) in seen:
                    continue
                seen.add(str(origin))
                record = delivery.snapshot(origin, relative)
                rtc = origin.with_suffix('.rtc')
                rtc_record = None
                if rtc.is_file():
                    rtc_rel = rtc.relative_to(root).as_posix()
                    delivery.safe_path(root, rtc_rel)
                    rtc_record = delivery.snapshot(rtc, rtc_rel)
                source_id = hashlib.sha256((str(root)+'\0'+relative+'\0'+record['sha256']+'\0'+
                    source['rom']['sha256']+'\0'+(rtc_record['sha256'] if rtc_record else '')).encode()).hexdigest()
                try:
                    body, clock, rule = convert(origin.read_bytes(), target, source['format'], rtc.read_bytes() if rtc_record else None)
                except ValueError as exc:
                    public['errors'].append(str(origin)+': '+str(exc))
                    continue
                candidate = {'id': source_id, 'root': str(root), 'format': source['format'], 'save': record,
                             'rom': source['rom'], 'rtc': rtc_record, 'rule': rule,
                             'body_sha256': hashlib.sha256(body).hexdigest(),
                             'rtc_sha256': hashlib.sha256(clock).hexdigest() if clock else None,
                             'guards': [source['rom'], record, *source['extra']] + ([rtc_record] if rtc_record else [])}
                public['candidates'].append(candidate)
                payloads[source_id] = body, clock
        candidates = public['candidates']
        if choice == 'skip':
            public['status'] = 'explicitly_skipped'
        elif choice:
            selected = next((c for c in candidates if c['id'] == choice), None)
            if not selected:
                raise ValueError('Chosen save source changed; inspect the new candidates')
            public.update(status='import', selected=[selected['id']])
        elif public['errors']:
            public['status'] = 'conflict'
        elif not candidates:
            public['status'] = 'no_source'
        elif (len({c['body_sha256'] for c in candidates}) == 1 and
              len({c['rtc_sha256'] for c in candidates if c['rtc_sha256']}) <= 1):
            public.update(status='import', selected=[c['id'] for c in candidates])
        else:
            public['status'] = 'conflict'
    return {'format': 'POCKET-PROGRESS-1', 'games': report,
            'imports': sum(r['status'] == 'import' for r in report),
            'native_instance_imports': sum(r['status'] == 'prepared_native_instance' for r in report),
            'conflicts': sum(r['status'] == 'conflict' for r in report),
            'existing_preserved': sum(r['status'] == 'keep_existing' for r in report),
            'existing_rtc_warnings': sum(r['status'] == 'keep_existing' and r['system'] == 'GBA' and bool(r['errors']) for r in report),
            'existing_save_warnings': sum(r['status'] == 'keep_existing' and bool(r['errors']) for r in report),
            'scope': 'Ordinary saves only; instant states and suspend files are never converted'}, payloads


def attach(card, components, base, out, parts, settings):
    report, payloads = collect(card, components, base, settings)
    delivery.write(out/'save-import-report.json', report)
    if report['conflicts']:
        raise Conflict(report)
    by_system = dict(parts)
    for row in report['games']:
        if row['status'] != 'import':
            continue
        candidates = [c for c in row['candidates'] if c['id'] in row['selected']]
        body = payloads[candidates[0]['id']][0]
        clocks = [payloads[c['id']][1] for c in candidates if payloads[c['id']][1] is not None]
        data = {row['path']: body}
        if clocks:
            data[str(PurePosixPath(row['path']).with_suffix('.rtc'))] = clocks[0]
        part = by_system[row['system']]
        for candidate in candidates:
            root = Path(candidate['root'])
            for guard in candidate['guards']:
                delivery.check_record(root, guard)
                if root == card:
                    part.setdefault('guards', []).append(guard)
                else:
                    part.setdefault('external_sources', []).append({'root': str(root), **guard})
        source = out/'imported-progress'
        for rel, raw in data.items():
            destination = delivery.allowed(source, rel, row['system'])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            part['changes'] = [c for c in part['changes'] if c['path'] != rel]
            part['changes'].append({**delivery.snapshot(destination, rel), 'source': str(source)})
        part.setdefault('summary', {})['ordinary_save_imports'] = part.get('summary', {}).get('ordinary_save_imports', 0) + 1
    return report
