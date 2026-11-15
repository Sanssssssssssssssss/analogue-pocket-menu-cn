#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package the fitted suspend-recovery/grayscale candidate with corresponding source."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import uuid
from prepare import prepare, ROOT

sys.path.insert(0, str(ROOT/'tools'))
import delivery
from build_release import RBF_SHA
from apf_metadata import check_core

FEATURES = ['suspend-timeout-guard', 'grayscale-all-scalers']
VERSION = '0.2.0-gb.1'


def package(build, previous, out, cheats=False):
    build, previous, out = map(lambda p: Path(p).resolve(), (build, previous, out))
    for path in (build, previous):
        delivery.separate(out, path)
    if out.exists():
        raise ValueError('Use a new package directory')
    reference = prepare(ROOT/'.work'/('gb-package-reference-'+uuid.uuid4().hex), cheats=cheats)
    version = '0.2.0-gb.2' if cheats else VERSION
    features = FEATURES+['PLCH1'] if cheats else FEATURES
    frozen = delivery.read(reference/'candidate-inputs.json')['files']
    compiled = {}
    for row in frozen:
        actual = build/row['path']
        if row['path'] == 'ap_core.qsf':
            # Quartus updates only the tool-version annotation on compilation.
            def qsf(path):
                return [line for line in path.read_text(encoding='utf8').splitlines()
                        if not line.startswith('set_global_assignment -name LAST_QUARTUS_VERSION ')]
            if qsf(actual) != qsf(reference/row['path']):
                raise ValueError('Compiled project assignment differs')
        elif row['path'] != 'apf/build_id.mif' and delivery.sha(actual) != row['sha256']:
            raise ValueError('Compiled candidate source differs: '+row['path'])
        compiled[row['path']] = delivery.sha(actual)
    output = build/'output_files'
    fit = (output/'ap_core.fit.summary').read_text()
    timing = (output/'ap_core.sta.summary').read_text()
    flow = (output/'ap_core.flow.rpt').read_text()
    slack = [float(s) for s in re.findall(r'Slack\s*:\s*(-?[\d.]+)', timing)]
    tns = [float(s) for s in re.findall(r'TNS\s*:\s*(-?[\d.]+)', timing)]
    if ('Fitter Status : Successful' not in fit or not re.search(r'Flow Status\s*[;:]\s*Successful', flow)
            or len(slack) < 40 or min(slack) < 0 or len(tns) != len(slack) or any(tns)):
        raise ValueError('Complete fitting and passing multicorner timing required')
    report = (output/'ap_core.sta.rpt').read_text()
    if not re.search(r'Unconstrained Clocks\s*;\s*0\s*;', report):
        raise ValueError('Unconstrained clocks require review')
    manifest = delivery.read(previous/'core/release-manifest.json')
    if manifest['bitstream_sha256'] != RBF_SHA:
        raise ValueError('Expected the retained accepted GB/GBC base package')
    for row in manifest['files']:
        delivery.check_record(previous/'core', row)
    shutil.copytree(previous/'core', out/'core')
    core = out/'core/Cores/pocketlab.CoverFlow'
    raw = (output/'ap_core.rbf').read_bytes()
    if not 1_000_000 < len(raw) < 3_000_000 or len(raw) % 4:
        raise ValueError('Unexpected raw FPGA image')
    table = bytes(int(f'{i:08b}'[::-1], 2) for i in range(256))
    (core/'gbc.rbf_r').write_bytes(raw.translate(table))
    digest = delivery.sha(core/'gbc.rbf_r')
    metadata = delivery.read(core/'core.json')
    metadata['core']['metadata'].update(version=version, date_release='2026-11-09' if cheats else '2026-11-08')
    delivery.write(core/'core.json', metadata)
    video = delivery.read(core/'video.json')
    ids = {int(mode['id'], 0) for mode in video['video'].get('display_modes', [])}
    video['video'].setdefault('display_modes', []).extend({'id': f'0x{i:02X}'} for i in range(0x20, 0x24) if i not in ids)
    delivery.write(core/'video.json', video)
    if cheats:
        data = delivery.read(core/'data.json')
        data['data']['data_slots'].append({'id':105, 'name':'Cheats', 'required':False, 'deferload':True,
                                          'parameters':'0x0', 'extensions':['cht'], 'size_maximum':'0x130'})
        delivery.write(core/'data.json', data)
    check_core(core)
    files = [delivery.snapshot(p, p.relative_to(out/'core').as_posix()) for p in sorted((out/'core').rglob('*'))
             if p.is_file() and p.name != 'release-manifest.json']
    manifest.update(version=version, bitstream_sha256=digest, files=files, features=features,
                    hardware_scope='New candidate: module regression and full fit/timing pass; device acceptance pending')
    delivery.write(out/'core/release-manifest.json', manifest)
    for rel in compiled:
        dest = delivery.safe_path(out/'sources', rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(build/rel, dest)
    receipt = {'core':'pocketlab.CoverFlow','version':version,'features':features,'bitstream_sha256':digest,
        'upgrade_from':[RBF_SHA], 'minimum_slack_ns':min(slack),'timing_records':len(slack),
        'fit':fit,'timing':timing,'source_inputs':compiled,'files':files,'hardware_acceptance':'pending',
        'timing_scope':'No unconstrained clocks; inherited external-port exceptions retained; not board-level signoff'}
    delivery.write(out/'build-receipt.json', receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build','previous','out'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--cheats', action='store_true')
    args = parser.parse_args()
    result = package(args.build, args.previous, args.out, args.cheats)
    print(json.dumps({k:result[k] for k in ('version','bitstream_sha256','minimum_slack_ns','timing_records')}, indent=2))
