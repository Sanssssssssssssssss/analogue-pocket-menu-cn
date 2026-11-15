#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Identify standard NTSC cartridges using the pinned SNES loader's header locations."""

import struct


def identify(path, size, *, allow_special=False):
    offset = size & 512
    payload = size - offset
    if not 32768 <= payload <= 16777216 or payload % 4:
        raise ValueError('Unsupported SNES cartridge length')

    headers = []
    with path.open('rb') as source:
        for mapper, address, mode in ((0,0x7fc0,0x20),(1,0xffc0,0x21),(2,0x40ffc0,0x25)):
            if address + 64 > payload:
                continue
            source.seek(offset+address)
            header = source.read(64)
            complement, checksum = struct.unpack_from('<HH',header,0x1c)
            paired_checksum = checksum != 0 and complement != 0 and checksum+complement == 0xffff
            detected = header[0x15] & 0xef
            special_mode = allow_special and (mapper, detected, header[0x16]) in {
                (0, 0x23, 0x32), (0, 0x23, 0x34), (0, 0x23, 0x35),
                (0, 0x22, 0x43), (0, 0x22, 0x45), (1, 0x2a, 0xf5), (1, 0x2a, 0xf9)
            }
            matches_mode = detected == mode or special_mode
            # The original LoROM check contributes no mode points. Its other
            # candidates prefer a scored ExHiROM header and break ties by address.
            score = 4*paired_checksum + 2*(header[0x1a]==0x33) + 2*(mapper!=0 and matches_mode)
            if mapper==2 and score:
                score += 4
            headers.append((score,mapper,header,paired_checksum,matches_mode))
    if not headers:
        raise ValueError('No complete SNES cartridge header')
    _, mapper, header, paired, matches = max(headers,key=lambda row:row[0])
    if not paired or not matches or struct.unpack_from('<H',header,0x3c)[0]<0x8000:
        raise ValueError('SNES header needs a valid mapping, checksum pair and reset vector')
    kind, ram, region = header[0x16], header[0x18], header[0x19]
    size_code = (payload-1).bit_length()-10
    return {'mapper': mapper, 'kind': kind, 'ram': ram, 'rom_offset': offset, 'size_code': size_code,
            'pal': 2 <= region <= 12 or region == 0x11}


def cartridge(path, size):
    info = identify(path, size)
    ram = info['ram']
    if info['kind'] not in (0, 1, 2) or ram > 7 or info['pal']:
        raise ValueError('PAL, special-chip or unsupported SRAM layout uses the original SNES core')
    return {'rom_config':info['mapper']|(info['size_code']<<8)|(ram<<12),'rom_offset':info['rom_offset'],
            'save_bytes':(1024<<ram) if ram else 0}
