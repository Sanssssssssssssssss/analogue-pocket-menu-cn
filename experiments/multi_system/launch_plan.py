#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline launch contracts. This does not install or launch an FPGA core."""
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
PROFILES = json.loads((HERE / 'profiles.json').read_text(encoding='utf-8'))


def inspect_rom(platform, data):
    """Validate container structure, never certify gameplay or a translated ROM."""
    profile = PROFILES[platform]
    if len(data) > profile['maximum_rom_bytes']:
        raise ValueError('ROM exceeds experiment size limit')
    if platform == 'gba':
        if len(data) < 192 or data[0xB2] != 0x96:
            raise ValueError('Invalid GBA fixed header byte or truncated header')
        if (sum(data[0xA0:0xBD]) + 0x19 + data[0xBD]) & 255:
            raise ValueError('Invalid GBA header checksum')
        markers = sorted(set(m.group().decode('ascii') for m in re.finditer(
            rb'(?:EEPROM|SRAM|FLASH1M|FLASH512|FLASH)_V[0-9]{3}', data)))
        return {'format': 'GBA', 'file_offset': 0, 'transfer_bytes': len(data),
                'save_markers': markers, 'save_detection': 'markers are hints; runtime core decides',
                'rtc': 'separate optional 16-byte slot; do not infer from title'}
    if platform == 'nes':
        if len(data) < 16 or data[:4] != b'NES\x1a':
            raise ValueError('Only iNES / NES 2.0 containers are accepted')
        nes2 = data[7] & 12 == 8
        trainer = 512 if data[6] & 4 else 0
        prg, chr_ = data[4] * 16384, data[5] * 8192
        mapper = (data[6] >> 4) | (data[7] & 0xF0)
        if nes2:
            if data[9] & 15 == 15 or data[9] >> 4 == 15:
                raise ValueError('NES 2.0 exponent sizes need a separate adapter')
            prg += (data[9] & 15) * 256 * 16384
            chr_ += (data[9] >> 4) * 256 * 8192
            mapper |= (data[8] & 15) << 8
        expected = 16 + trainer + prg + chr_
        if not prg or len(data) != expected:
            raise ValueError('NES size differs from declared PRG/CHR/trainer payload')
        return {'format': 'NES 2.0' if nes2 else 'iNES', 'file_offset': 0,
                'transfer_bytes': len(data), 'mapper': mapper, 'trainer_bytes': trainer,
                'header_handling': 'send intact; upstream loader parses header and trainer',
                'mapper_compatibility': 'not certified by this check'}
    # SNES mapper and bitstream selection belong to the actual upstream Chip32.
    offset = 512 if len(data) % 1024 == 512 else 0
    if len(data) - offset < 32768 or (len(data) - offset) % 1024:
        raise ValueError('Unsupported SNES file length')
    candidates = []
    for name, location in [('LoROM', 0x7FC0), ('HiROM', 0xFFC0), ('ExHiROM', 0x40FFC0)]:
        p = location + offset
        if p + 32 <= len(data):
            complement = int.from_bytes(data[p+28:p+30], 'little')
            checksum = int.from_bytes(data[p+30:p+32], 'little')
            if checksum and complement and checksum + complement == 0xFFFF:
                candidates.append({'location': name, 'map_mode': data[p+21],
                                   'cartridge_type': data[p+22], 'region': data[p+25]})
    if not candidates:
        raise ValueError('No plausible SNES header; do not guess the bitstream')
    return {'format': 'SNES', 'file_offset': offset, 'transfer_bytes': len(data)-offset,
            'header_candidates': candidates, 'loader': 'upstream support/loader.asm',
            'bitstream': 'must be selected by upstream loader; never force main'}


def make_plan(platform, data, title='测试游戏'):
    info = inspect_rom(platform, data)
    profile = PROFILES[platform]
    digest = hashlib.sha256(data).hexdigest()
    return {'platform': platform, 'title': title, 'rom_sha256': digest,
            'source': {'repository': profile['repository'], 'commit': profile['commit']},
            'rom': {'slot': profile['rom_slot'], 'address': profile['rom_address'], **info},
            'experimental_save': f'Saves/cn{platform}/common/{digest[:20]}.sav',
            'experimental_rtc': f'Saves/cn{platform}/common/{digest[:20]}.rtc' if platform == 'gba' else None,
            'launch_route': profile['launch_route'], 'deployable': False,
            'missing': ['integrate menu with game core reset/video/memory',
                        'load and flush isolated ordinary saves before handoff',
                        'full combined-core fit/timing and hardware acceptance'],
            'file_writes': 0}


def check_upstream(sources):
    """Compare frozen contracts to independently downloaded actual core metadata."""
    for platform, profile in PROFILES.items():
        data = json.loads((Path(sources)/platform/profile['data_json']).read_text())
        slots = {s['id']: s for s in data['data']['data_slots']}
        for key in ('rom', 'save'):
            assert int(slots[profile[key+'_slot']]['address'], 0) == int(profile[key+'_address'], 0), platform
        if platform == 'gba':
            assert slots[4]['size_exact'] == 16384
            assert slots[11]['size_exact'] == 16
            assert int(slots[1]['size_maximum'], 0) == profile['maximum_rom_bytes']
        if platform == 'snes':
            core_path = Path(sources)/platform/profile['data_json'].replace('data.json', 'core.json')
            core = json.loads(core_path.read_text())
            names = [b['name'] for b in core['core']['cores']]
            assert names == profile['bitstreams'], names
    return list(PROFILES)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--platform', choices=PROFILES)
    p.add_argument('--rom', type=Path)
    p.add_argument('--check-upstream', type=Path)
    a = p.parse_args()
    if a.check_upstream:
        print(json.dumps({'matched_profiles': check_upstream(a.check_upstream)}))
    elif a.platform and a.rom:
        print(json.dumps(make_plan(a.platform, a.rom.read_bytes(), a.rom.stem), ensure_ascii=False, indent=2))
    else:
        p.error('Use --check-upstream or --platform and --rom')
