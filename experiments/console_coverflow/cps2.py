#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read CPS2 Pocket instances into native ROM, NVRAM and control plans."""

import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from install import safe_path, sha

ASSETS = PurePosixPath('Assets/jtcps2/common')
INSTANCE_ROOTS = (ASSETS, ASSETS.with_name('jotego.jtcps2'))
CONTROLS = {0xf9000000: 'core_mode', 0xfa000000: 'dip_switches', 0xfc000000: 'button_map'}
DEFAULT_BUTTON_MAP = 0x543210  # JTFRAME Pocket reset mapping
BRIDGE_SHA = 'b32af6df8785e61f2adcdb1a156cc2dd4f181caec2e9c9cf6ef2766c4de1bd79'


def save_id(rom_digest, core_mode, button_map, dip_switches):
    settings = struct.pack('<III', core_mode, button_map, dip_switches)
    return hashlib.sha256(bytes.fromhex(rom_digest) + settings).hexdigest()[:20]


def uint(value):
    if isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]+',value):
        value = int(value,16)
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        raise ValueError('Expected an unsigned 32-bit instance value')
    return value


def relative(value):
    if not isinstance(value,str) or len(value.encode('utf8'))>255:
        raise ValueError('Invalid instance path')
    if value and any(part in ('','.','..') for part in value.rstrip('/').split('/')):
        raise ValueError('Instance path must be relative to its own folder')
    return value.rstrip('/')


def instance_files(root):
    for directory in INSTANCE_ROOTS:
        for path in sorted(safe_path(root, directory.as_posix()).rglob('*')):
            if path.is_file() and path.suffix.lower() == '.json':
                yield path


def instance_inputs(root, instance_path):
    rel = PurePosixPath(relative(instance_path))
    if not any(rel.is_relative_to(directory) for directory in INSTANCE_ROOTS) or rel.suffix.lower() != '.json':
        raise ValueError('Expected a CPS2 JSON instance under Assets/jtcps2/common or jotego.jtcps2')
    path = safe_path(root,rel.as_posix())
    instance = json.loads(path.read_text(encoding='utf-8-sig'))['instance']
    if not isinstance(instance,dict) or instance.get('magic')!='APF_VER_1':
        raise ValueError('Invalid APF instance version')
    if set(instance)-{'magic','data_path','core_select','variant_select','data_slots','memory_writes'}:
        raise ValueError('Instance has unsupported options')
    for key in ('core_select','variant_select'):
        selection = instance.get(key,{'id':0,'select':False})
        if uint(selection['id'])!=0 or selection['select'] is not False:
            raise ValueError('Only the native default CPS2 bitstream is supported')
    slots, rom_md5 = {}, None
    for row in instance['data_slots']:
        slot = uint(row['id'])
        if slot in slots or slot not in (1,2):
            raise ValueError('Unsupported or duplicate CPS2 slot')
        name = relative(row['filename'])
        if PurePosixPath(name).suffix.lower()!=('.rom' if slot==1 else '.sav'):
            raise ValueError('Unexpected CPS2 file extension')
        if slot == 1 and 'md5' in row:
            rom_md5 = row['md5']
            if not isinstance(rom_md5, str) or not re.fullmatch(r'[0-9a-fA-F]{32}', rom_md5):
                raise ValueError('Invalid CPS2 instance ROM checksum')
        slots[slot] = name
    if slots.keys()!={1,2}:
        raise ValueError('CPS2 instance needs ROM and NVRAM filenames')

    settings = {}
    for row in instance.get('memory_writes',[]):
        addr, value = uint(row['address']), uint(row['data'])
        if addr not in CONTROLS or CONTROLS[addr] in settings:
            raise ValueError('Unsupported or duplicate CPS2 control register')
        settings[CONTROLS[addr]] = value
    settings.setdefault('button_map', DEFAULT_BUTTON_MAP)
    settings.setdefault('dip_switches',0xffffffff)
    if 'core_mode' not in settings or settings['button_map'] > 0xffffff:
        raise ValueError('CPS2 instance needs a core mode and a 24-bit button mapping')

    # Jotego's instance slot is core-specific. The ROM and NVRAM slots are common.
    base = rel.parent if rel.is_relative_to(ASSETS) else ASSETS
    folder = base/relative(instance.get('data_path',''))
    rom = safe_path(root, (folder/slots[1]).as_posix())
    if not rom.is_file():
        raise ValueError('CPS2 instance ROM is missing')
    size = rom.stat().st_size
    if size<=44 or size>64*1024**2 or size%4:
        raise ValueError('Unexpected CPS2 image size')
    native_save = PurePosixPath('Saves/jtcps2/common')/(folder/slots[2]).relative_to(ASSETS)
    safe_path(root, native_save.as_posix())
    return path, rom, size, rom_md5, slots[2], native_save.as_posix(), settings


def available_instances(root):
    for path in instance_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            instance_inputs(root, rel)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        yield rel


def plan(root, instance_path):
    root = Path(root).resolve()
    path, rom, size, rom_md5, save_name, native_save, settings = instance_inputs(root, instance_path)
    if rom_md5 is None:
        digest = sha(rom)
    else:
        rom_hash, checksum = hashlib.sha256(), hashlib.md5()
        with rom.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                rom_hash.update(chunk)
                checksum.update(chunk)
        if checksum.hexdigest() != rom_md5.lower():
            raise ValueError('CPS2 instance ROM checksum differs')
        digest = rom_hash.hexdigest()
    instance_digest = sha(path)
    binding = save_id(digest, settings['core_mode'], settings['button_map'], settings['dip_switches'])
    return {'instance':path.relative_to(root).as_posix(),'instance_sha256':instance_digest,'title':path.stem,
            'rom':{'slot':1,'path':rom.relative_to(root).as_posix(),'bytes':size,'sha256':digest},
            'nvram':{'slot':2,'bytes':128,'instance_filename':save_name,'original_path':native_save,
                     'candidate_path':f'Saves/cpslab/common/{binding}.sav'},
            **settings}


def prepare_bridge(source, out):
    """Generate the checked JTFRAME command bridge for offline integration."""
    source, out = Path(source), Path(out).resolve()
    if out.exists() or not out.is_relative_to(Path(__file__).resolve().parents[2]/'.work'):
        raise ValueError('Fresh local output under .work required')
    if sha(source)!=BRIDGE_SHA:
        raise ValueError('Unexpected JTFRAME command bridge source')
    text=source.read_text(encoding='utf8')
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:
            raise ValueError('JTFRAME command bridge anchor changed')
        text=text.replace(old,new)
    replace('    output reg        inmenu\n', '''    input wire menu_game_bound,
    input wire [31:0] menu_open_parameter,
    input wire target_cmd_req,
    input wire [15:0] target_cmd,
    input wire [31:0] target_cmd_p0, target_cmd_p1, target_cmd_p2, target_cmd_p3,
    output wire target_cmd_ack, target_cmd_done,
    output wire [15:0] target_cmd_result,
    output reg inmenu
''')
    replace('    if(sys_rd) begin\n        casez(sys_addr32)', '''    if(sys_rd) begin
        if (target_read_selected) sys_din <= target_read_data;
        else casez(sys_addr32)''')
    replace('sys_addr32[2] ? NVRAM_SIZE : IDX_NVRAM',
            'sys_addr32[2] ? (menu_game_bound ? NVRAM_SIZE : 0) : IDX_NVRAM')
    replace('endmodule', '''wire target_read_selected;
wire [31:0] target_read_data;
cps2_target runtime_target (
    .clk(clk),.running(rst_req_n),.reset_enter(hcmd_go && hcmd==16'h0010),
    .address(sys_addr32),.host_data(sys_dout),.open_parameter(menu_open_parameter),.host_write(sys_wr),
    .read_selected(target_read_selected),.read_data(target_read_data),
    .request(target_cmd_req),.command(target_cmd),.p0(target_cmd_p0),.p1(target_cmd_p1),
    .p2(target_cmd_p2),.p3(target_cmd_p3),.ack(target_cmd_ack),.done(target_cmd_done),.result(target_cmd_result)
);
endmodule''')
    out.mkdir(parents=True)
    (out/source.name).write_text(text,encoding='utf8',newline='\n')
    shutil.copy2(Path(__file__).with_name('cps2_target.sv'),out/'cps2_target.sv')
    return out


if __name__ == '__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--source',type=Path,required=True)
    cli.add_argument('instance',help='SD-relative path of the existing CPS2 instance JSON')
    args=cli.parse_args()
    print(json.dumps(plan(args.source,args.instance),ensure_ascii=False,indent=2))
