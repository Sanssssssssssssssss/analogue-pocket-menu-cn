# SPDX-License-Identifier: MIT
"""Synthetic container bytes only; these are not runnable games or BIOS."""
def gba():
    data = bytearray(32768)
    data[0xA0:0xAC] = b'MENU PROBE  '
    data[0xB2] = 0x96
    data[0xBD] = (-sum(data[0xA0:0xBD])-0x19) & 255
    data[4096:4107] = b'SRAM_V113\0\0'
    return data


def nes(trainer=False, nes2=False):
    data = bytearray(16 + 16384 + 8192 + (512 if trainer else 0))
    data[:4] = b'NES\x1a'
    data[4:6] = bytes([1, 1])
    data[6] = 4 if trainer else 0
    data[7] = 8 if nes2 else 0
    return data


def snes(kind='lorom', pal=False, chip=0, copier=False):
    # Header values selected to exercise the real upstream loader.
    size = 0x420000 if kind == 'exhirom' else 0x20000
    offset = 512 if copier else 0
    data = bytearray(size+offset)
    h = {'lorom':0x7FC0, 'hirom':0xFFC0, 'exhirom':0x40FFC0}[kind]+offset
    data[h:h+21] = b'MENU SYNTHETIC PROBE '
    data[h+21] = {'lorom':0x20, 'hirom':0x21, 'exhirom':0x25}[kind]
    data[h+22] = chip
    if chip == 0x43: data[h+21] = 0x32  # S-DD1
    if chip == 0xF9: data[h+21] = 0x3A  # SPC7110
    data[h+23:h+28] = bytes([6, 3, 2 if pal else 1, 0x33, 0])
    data[h+28:h+32] = b'\xCB\xED\x34\x12'
    data[h+60:h+62] = b'\x00\x80'
    return data
