#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package a fully fitted Atari candidate with checked native slot identities."""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import struct
import sys
import uuid
from pathlib import Path

_spec = importlib.util.spec_from_file_location('atari_package_prepare', Path(__file__).with_name('prepare.py'))
adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(adapter)
ROOT, PROFILES = adapter.ROOT, adapter.PROFILES
sys.path.insert(0, str(ROOT/'tools'))
from apf_metadata import check_core, check_candidate_bitstream
from PIL import Image, ImageDraw
import build_library
from platform_frontend import encode


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metadata(platform, original):
    namespace = PROFILES[platform][0]
    result = {name: json.loads((original/(name+'.json')).read_text(encoding='utf8')) for name in
              ('core', 'data', 'video', 'audio', 'input', 'interact', 'variants')}
    core = result['core']['core']
    core['metadata'].update(platform_ids=[namespace, platform], author='pocketlab', shortname='Atari'+platform,
        description='Chinese CoverFlow. Native shared saves; Pocket Quit exits.',
        url='https://github.com/Sanssssssssssssssss/analogue-pocket-menu-cn', version='0.1.0-'+platform+'.1', date_release='2026-11-15')
    core['cores'] = [{'name': 'default', 'id': 0, 'filename': platform+'.rbf_r'}]
    slots = result['data']['data']['data_slots']
    expected = [0x100, 0x107, 0x105, 0x10a] if platform == '2600' else [0x100, 0x103, 0x104, 0x105, 0x106, 0x107, 0x108, 0x109, 0x10a]
    if [int(str(s['id']), 0) for s in slots] != expected:
        raise ValueError('Native slot order changed; datatable index must be preserved')
    for slot in slots:
        flags = int(str(slot['parameters']), 0)
        slot['parameters'] = hex(flags | 0x01000000)
    slots[0].update(required=False, deferload=True, parameters='0x01000008')
    slots.append(dict(id=100, name='Chinese Menu', required=True, deferload=True, parameters='0x8', filename='menu.bin',
                      extensions=['bin'], address='0x70000000', size_maximum='0x10000000'))
    video = result['video']['video']['scaler_modes']
    if len(video) != (2 if platform == '2600' else 8):
        raise ValueError('Native video modes changed')
    if platform == '2600':
        video.append(dict(width=320, height=288, aspect_w=10, aspect_h=9, rotation=0, mirror=0))
    elif (video[4]['width'], video[4]['height']) != (320, 274):
        raise ValueError('7800 menu requires the original PAL scaler slot')
    return result


def stage(platform, build, archive, gba_source, out):
    build, out = Path(build).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work') or build.is_relative_to(out) or out.is_relative_to(build):
        raise ValueError('Use a fresh separate .work staging directory')
    reports = build/'src/fpga/output_files'
    def read(suffix):
        return (reports/('ap_core.'+suffix)).read_text(encoding='latin1')
    fit, timing, flow = read('fit.summary'), read('sta.summary'), read('flow.rpt')
    if 'Fitter Status : Successful' not in fit or not re.search(r'Flow Status\s*[;:]\s*Successful', flow):
        raise ValueError('Full fit/assembly/STA required')
    slacks = [float(s) for s in re.findall(r'Slack\s*:\s*(-?[\d.]+)', timing)]
    tns = [float(s) for s in re.findall(r'TNS\s*:\s*(-?[\d.]+)', timing)]
    corners = ['Slow 1100mV 85C', 'Slow 1100mV 0C', 'Fast 1100mV 85C', 'Fast 1100mV 0C']
    if len(slacks) < 40 or min(slacks) < 0 or len(slacks) != len(tns) or any(tns) or any(c not in timing for c in corners):
        raise ValueError('Incomplete or failing four-corner STA')
    for suffix in ('map.rpt', 'fit.rpt', 'sta.rpt', 'asm.rpt'):
        critical = [line.strip() for line in read(suffix).splitlines() if 'Critical Warning (' in line]
        if critical:
            raise ValueError('Unreviewed critical warnings: '+str(critical[:4]))
    reference = adapter.prepare(platform, archive, gba_source, ROOT/'.work/repair-20261115'/('atari-package-reference-'+uuid.uuid4().hex))
    inputs = {}
    for file in reference.rglob('*'):
        if not file.is_file():
            continue
        relative = file.relative_to(reference)
        actual = build/relative
        if not actual.is_file():
            raise ValueError('Compiled source missing: '+relative.as_posix())
        expected, compiled = file.read_bytes(), actual.read_bytes()
        if relative.as_posix() == 'src/fpga/ap_core.qsf':
            ignored = ('set_global_assignment -name LAST_QUARTUS_VERSION ', 'set_global_assignment -name SEED ')
            expected, compiled = ([line for line in data.decode().splitlines() if not line.startswith(ignored)] for data in (expected, compiled))
        elif relative.as_posix() == 'src/fpga/apf/build_id.mif':
            expected, compiled = (re.sub(rb'(?m)^(   0E[012] : )[0-9a-fA-F]{8};$', rb'\g<1>00000000;', data.replace(b'\r\n', b'\n')) for data in (expected, compiled))
        if expected != compiled:
            raise ValueError('Compiled source differs from deterministic preparation: '+relative.as_posix())
        inputs[relative.as_posix()] = sha(actual)
    raw = (reports/'ap_core.rbf').read_bytes()
    if not 1024**2 <= len(raw) <= 3*1024**2 or len(raw) % 4:
        raise ValueError('Unexpected FPGA bitstream size')
    namespace = PROFILES[platform][0]
    original = reference/'dist/Cores'/('Miasmark.'+platform)
    documents = metadata(platform, original)
    core_name = 'pocketlab.Atari'+platform
    package = out/'core'
    target = package/'Cores'/core_name
    target.mkdir(parents=True)
    for name, value in documents.items():
        (target/(name+'.json')).write_text(json.dumps(value, indent=2)+'\n', encoding='utf8', newline='\n')
    reverse = bytes(int(f'{i:08b}'[::-1], 2) for i in range(256))
    bitstream = target/(platform+'.rbf_r')
    bitstream.write_bytes(raw.translate(reverse))
    check_core(target)
    digest = check_candidate_bitstream(bitstream)
    platform_dir = package/'Platforms'
    platform_dir.mkdir(parents=True)
    (platform_dir/(namespace+'.json')).write_text(json.dumps({'platform': {'category': 'CN Menu', 'name': 'Atari '+platform+' Menu CN',
        'manufacturer': 'Pocket Lab', 'year': 2026}}, indent=2)+'\n', encoding='utf8')
    # Original project-owned banner; no upstream release artwork is copied.
    image = Image.new('L',(521,165),0)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((15,56,160,136),radius=9,outline=210,width=3)
    draw.rectangle((29,72,145,91),outline=130,width=2)
    for x in (43,58,73,88,103,118):
        draw.line((x,98,x,123),fill=95,width=2)
    draw.rectangle((73,38,101,66),outline=210,width=3)
    draw.ellipse((24,26,48,48),outline=190,width=3)
    draw.line((36,38,36,60),fill=220,width=4)
    for title,y,scale in [('ATARI '+platform,44,3),('中文游戏菜单',105,2)]:
        width,raw,clipped,missing=build_library.columns(title,build_library.font())
        if missing or clipped:
            raise ValueError('Platform banner glyph is missing')
        glyph=Image.new('L',(width,16),0)
        pixels=ImageDraw.Draw(glyph)
        for x,column in enumerate(struct.unpack('<512H',raw)[:width]):
            for row in range(16):
                if column>>row&1:
                    pixels.point((x,row),fill=235)
        image.paste(glyph.resize((width*scale,16*scale),Image.Resampling.NEAREST),(185,y))
    (platform_dir/'_images').mkdir()
    (platform_dir/'_images'/(namespace+'.bin')).write_bytes(encode(image))
    image.save(out/'platform.png')
    receipt = {'core': core_name, 'namespace': namespace, 'version': documents['core']['core']['metadata']['version'],
        'menu_format': 'GBAF2/'+platform, 'bitstream_sha256': digest,
        'upstream_commit': PROFILES[platform][1], 'upstream_archive_sha256': PROFILES[platform][2], 'rbf_r_sha256': digest,
        'timing_records': len(slacks), 'minimum_slack_ns': min(slacks), 'tns': 0, 'fit': fit, 'timing': timing,
        'source_inputs': inputs, 'hardware_acceptance': 'pending', 'native_save_slots_preserved': True,
        'exit': 'Pocket Quit', 'files': []}
    for file in sorted(package.rglob('*')):
        if file.is_file():
            receipt['files'].append({'path': file.relative_to(package).as_posix(), 'bytes': file.stat().st_size, 'sha256': sha(file)})
    (out/'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf8')
    for relative in inputs:
        target_source = out/'sources'/relative
        target_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(build/relative, target_source)
    return receipt


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('platform', choices=PROFILES)
    for key in ('build', 'archive', 'gba-source', 'out'):
        cli.add_argument('--'+key, type=Path, required=True)
    args = cli.parse_args()
    result = stage(args.platform, args.build, args.archive, args.gba_source, args.out)
    print(json.dumps({key: result[key] for key in ('core', 'rbf_r_sha256', 'timing_records', 'minimum_slack_ns', 'hardware_acceptance')}))
