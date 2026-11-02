# SPDX-License-Identifier: MIT
"""Recognize legacy .sms-named Game Gear images without renaming ROMs."""
import hashlib
import zlib

# SMS Power documents system nibbles 5/6/7 as GG, but warns of bad headers.
# This GG release legitimately has an SMS header. Identify its bytes instead.
# https://www.smspower.org/Development/ROMHeader
# libretro/libretro-database da577d2865c2b1b834b2d5f2fd1368fc5110a01c,
# metadat/no-intro/Sega - Game Gear.dat (Excellent Dizzy Collection, Europe).
LEGACY_GG={(524288,'db3c0686715373242911f8471a1e91673811d62a',0xaa140c9c)}


def legacy_gamegear(raw):
    if len(raw)%16384==512:return False  # Native loader does not strip copier headers.
    regions=set()
    for offset in (0x1ff0,0x3ff0,0x7ff0):
        header=raw[offset:offset+16]
        if len(header)==16 and header[:8]==b'TMR SEGA':regions.add(header[15]>>4)
    if regions and regions.issubset({5,6,7}):return True
    if len(raw) not in {entry[0] for entry in LEGACY_GG}:return False
    return (len(raw),hashlib.sha1(raw).hexdigest(),zlib.crc32(raw)&0xffffffff) in LEGACY_GG
