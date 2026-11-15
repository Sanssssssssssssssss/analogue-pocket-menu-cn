#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile explicitly curated, exact-ROM read replacements into bounded PLCH files."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

PLATFORMS = {'gb': (1,16,8,0,0x7fff), 'gbc': (2,16,8,0,0x7fff),
             'nes': (3,16,8,0x8000,0xffff), 'pce': (4,21,8,0,0x1fffff),
             'genesis': (5,24,16,0,0x3fffff), 'snes': (6,24,8,0,0xffffff)}


def encode(platform, digest, codes):
    identity, address_bits, data_bits, low, high = PLATFORMS[platform]
    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Full lowercase ROM SHA256 required')
    if not 1 <= len(codes) <= 16:
        raise ValueError('One to sixteen supported read replacements required')
    body = bytearray(bytes.fromhex(digest))
    seen = set()
    for row in codes:
        if set(row)-{'type','address','value','compare'} or row.get('type') != 'read_replace':
            raise ValueError('Unsupported native cheat mechanism; encrypted and RAM-write codes require a decoder')
        address, value, compare = row['address'], row['value'], row.get('compare')
        if type(address) is not int or not low <= address <= high or address >= 1 << address_bits:
            raise ValueError('Cheat address is outside the supported native ROM range')
        if type(value) is not int or not 0 <= value < 1 << data_bits:
            raise ValueError('Replacement exceeds the native data width')
        if compare is not None and (type(compare) is not int or not 0 <= compare < 1 << data_bits):
            raise ValueError('Comparison exceeds the native data width')
        if platform == 'genesis' and address & 1:
            raise ValueError('MD 16-bit ROM replacements require even addresses')
        if platform == 'snes' and (address >> 16 in (0x7e,0x7f) or not address & 0x8000):
            raise ValueError('SFC replacements are restricted to mapped ROM addresses')
        if address in seen:
            raise ValueError('One curated replacement per address; conflicting or stacked records refused')
        seen.add(address)
        body += struct.pack('<4I', int(compare is not None), address, compare or 0, value)
    return struct.pack('<4I', 0x48434c50, 0x10000 | identity, len(codes), zlib.crc32(body)) + body


def profiles(path):
    value = json.loads(Path(path).read_text(encoding='utf-8-sig')) if path else {'format':'POCKET-CHEATS1','profiles':[]}
    if value.get('format') != 'POCKET-CHEATS1':
        raise ValueError('Expected a POCKET-CHEATS1 version-bound index')
    result = {}
    for row in value['profiles']:
        key = row['platform'], row['sha256']
        if row['platform'] not in PLATFORMS or key in result:
            raise ValueError('Unsupported platform or duplicate ROM profile')
        source = row['source']
        if not isinstance(source,dict) or not source.get('license') or not str(source.get('url','')).startswith('https://'):
            raise ValueError('Cheat source URL and license must be recorded')
        if type(row['bytes']) is not int or row['bytes'] < 192:
            raise ValueError('Expected exact ROM byte length')
        effects = row['effects']
        if not 1 <= len(effects) <= 2 or any(not e.get('title') or e.get('enabled') is not True for e in effects):
            raise ValueError('One or two named, explicitly enabled practical effects required')
        encode(row['platform'], row['sha256'], [code for effect in effects for code in effect['codes']])
        result[key] = row
    return result


def payload(profile, raw):
    if hashlib.sha256(raw).hexdigest() != profile['sha256'] or len(raw) != profile['bytes']:
        raise ValueError('Cheat profile belongs to a different ROM version')
    return encode(profile['platform'], profile['sha256'], [code for effect in profile['effects'] for code in effect['codes']])


def decode(raw, platform, digest):
    """Revalidate a previously generated payload against the complete ROM digest."""
    if len(raw) < 64 or len(raw) > 304 or len(raw) % 16:
        raise ValueError('Invalid native cheat file length')
    magic, version, count, crc = struct.unpack_from('<4I', raw)
    if (magic != 0x48434c50 or version != 0x10000 | PLATFORMS[platform][0]
            or not 1 <= count <= 16 or len(raw) != 48+16*count
            or zlib.crc32(raw[16:]) != crc or raw[16:48].hex() != digest):
        raise ValueError('Native cheat identity, header or checksum differs')
    records = []
    for offset in range(48, len(raw), 16):
        flags, address, compare, value = struct.unpack_from('<4I', raw, offset)
        if flags not in (0, 1) or (not flags and compare):
            raise ValueError('Invalid native cheat comparison flags')
        record = {'type':'read_replace', 'address':address, 'value':value}
        if flags:
            record['compare'] = compare
        records.append(record)
    if encode(platform, digest, records) != raw:
        raise ValueError('Noncanonical native cheat payload')
    return records


def collect_payloads(card, refs, platform, namespace, index):
    import delivery
    candidates = profiles(index)
    payloads, used, guards = {}, {}, []
    for ref in refs:
        delivery.check_record(card, ref)
        target_platform = ref['path'].split('/')[1] if platform == 'gb-family' else platform
        profile = candidates.get((target_platform, ref['sha256']))
        if profile:
            data = payload(profile, delivery.safe_path(card, ref['path']).read_bytes())
            relative = f'Assets/{namespace}/cheat/{ref["sha256"][:20]}.cht'
            if relative in payloads and payloads[relative][8:] != data[8:]:
                raise ValueError('The same ROM has conflicting native cheat profiles')
            payloads[relative] = data
            used[ref['sha256'][:20]] = {'path': relative, 'rom_sha256': ref['sha256'],
                'source': profile['source'], 'effects': [effect['title'] for effect in profile['effects']]}
        elif index is None:
            relative = f'Assets/{namespace}/cheat/{ref["sha256"][:20]}.cht'
            previous = delivery.safe_path(card, relative)
            if previous.is_file():
                data = previous.read_bytes()
                # Identical bytes may appear in both the GB and GBC source folders.
                if platform == 'gb-family':
                    header = int.from_bytes(data[4:8], 'little')
                    target_platform = 'gbc' if header == 0x10002 else 'gb'
                decode(data, target_platform, ref['sha256'])
                payloads[relative] = data
                guards.append(delivery.snapshot(previous, relative))
                used[ref['sha256'][:20]] = {'path':relative, 'rom_sha256':ref['sha256'],
                    'source':{'kind':'retained-exact-ROM-payload','sha256':delivery.sha(previous)},
                    'effects':['Retained matching enabled codes']}
    return payloads, used, guards


def bind_library(card, library, platform, index=None):
    """Bind fresh native pages to optional exact-ROM code files."""
    import delivery
    card, library = Path(card).resolve(), Path(library).resolve()
    delivery.separate(card, library)
    namespace = {'nes':'neslab','pce':'pcelab','genesis':'mdclab','snes':'snescn','gb-family':'gbclab'}.get(platform)
    if namespace is None:
        raise ValueError('No verified library adapter for this platform')
    manifest = delivery.read(library/'library-manifest.json')
    is_gb = platform == 'gb-family'
    expected_format = 9 if is_gb else 'GBAF2/'+{'nes':'NES','snes':'SNES'}.get(platform, platform)
    if manifest.get('format') != expected_format or manifest.get('features'):
        raise ValueError('A fresh unextended matching native library is required')
    files = {row['path']: row for row in manifest['files']}
    payloads, used, guards = collect_payloads(card, manifest['source_refs'], platform, namespace, index)
    for relative, record in list(files.items()):
        if relative.endswith('/gbc_bios.bin'):
            continue
        if not relative.startswith(f'Assets/{namespace}/common/') or not relative.endswith('.bin'):
            continue
        path = delivery.safe_path(library, relative)
        delivery.check_record(library, record)
        raw = bytearray(path.read_bytes())
        if is_gb:
            from style_library import decode as decode_page
            from build_library import path_bytes
            entries = decode_page(raw)['entries']
            extra_paths = []
            matched = False
            for i, entry in enumerate(entries):
                tag = Path(entry['paths'][1]).stem
                cheat = f'/Assets/{namespace}/cheat/{tag}.cht'
                size = 0 if entry['record'][40] & 128 else len(payloads.get(cheat[1:], b''))
                matched |= bool(size)
                struct.pack_into('<H', raw, 528+i*128+42, size)
                extra_paths.append(path_bytes(cheat) if size else bytes(256))
            if matched:
                raw += b''.join(extra_paths)
        else:
            count = int.from_bytes(raw[8:12], 'little')
            for index_ in range(count):
                offset = 64+index_*1024
                save = raw[offset+288:offset+544].split(b'\0',1)[0].decode('utf8')
                tag = Path(save).stem
                cheat = f'/Assets/{namespace}/cheat/{tag}.cht'
                raw[offset+544:offset+800] = cheat.encode().ljust(256,b'\0')
                struct.pack_into('<I', raw, offset+(16 if platform=='nes' else 804), len(payloads.get(cheat[1:],b'')))
        path.write_bytes(raw)
        files[relative] = delivery.snapshot(path, relative)
    for relative, raw in payloads.items():
        path = delivery.safe_path(library, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        files[relative] = delivery.snapshot(path, relative)
    manifest.update(features=['PLCH1'], files=list(files.values()), cheats=list(used.values()), cheat_source_refs=guards)
    delivery.write(library/'library-manifest.json', manifest)
    return manifest
