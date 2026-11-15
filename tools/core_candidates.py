# SPDX-License-Identifier: MIT
"""Explicitly reviewed native candidates and preserving upgrade rules."""
from pathlib import Path

import delivery
from apf_metadata import check_core

CATALOG = {
    'GB-GBC': {
        '49630de870def730de618dcfb39343ed8b11058da6e2d4db7eb2885bece59178': {
            'version': '0.2.0-gb.2', 'features': ['suspend-timeout-guard', 'grayscale-all-scalers', 'PLCH1'],
            'receipt_sha256': '0b5b961ad177dcbda280dadffd34c89e18b5943e19e410738077cc8fcf27a0f6',
            'from': ['1cb62f954484be8c002e2f6c74e7813d34ef0cbe2fb910f3916dab1c43d766d9',
                     'e9f538535d6962e042e58cf6b51854492b701ce85aa3acb1272a477df868244b']},
        'e9f538535d6962e042e58cf6b51854492b701ce85aa3acb1272a477df868244b': {
            'version': '0.2.0-gb.1', 'features': ['suspend-timeout-guard', 'grayscale-all-scalers'],
            'receipt_sha256': '9ec35af3a484c2fff25eb7ce0a2111fb1f11e2bffc88feceea08edb07cf6afe3',
            'from': ['1cb62f954484be8c002e2f6c74e7813d34ef0cbe2fb910f3916dab1c43d766d9']}
    },
    'NES': {
        '549109bea22d76f9214988724f3af6a94dc16e57b46b6dae3801bd90eb334c94': {
            'version': '0.4.0-nes.1', 'features': ['PLCH1'],
            'receipt_sha256': '961a9e29765bb10df360e35a9894cc14f8191cc6cef08eba56fd55666dc33cd3',
            'from': ['9d7d46dfe0e219dac682bf905f61736da9d83191225fd5500245c44cd929ac49']}
    },
    'MD': {
        'c6fdb6d1fbfc5379f7431354d8e6083e13e47d92cfd91b44948e6854085f5334': {
            'version': '0.4.0-md.2', 'features': ['PLCH1'],
            'receipt_sha256': '24e17e9d91b1ed2782826e1ab0ed96aec06616096aa00e2becd2446de977d81c',
            'from': ['94a23b8200f35ae087f152f4d19c5f30c9aab0f16c96bf14f1208f0f303c1784',
                     '768f11d29fa3f08763fe2c49ee8170153799a2eed60488ea1ec0a26589c1d4eb']},
        '768f11d29fa3f08763fe2c49ee8170153799a2eed60488ea1ec0a26589c1d4eb': {
            'version': '0.4.0-md.1', 'features': ['PLCH1'],
            'receipt_sha256': '7043d4ffc0c837a8f23a78d82ee7f269d02a73993531e267d781ab598cc4c7d2',
            'from': ['94a23b8200f35ae087f152f4d19c5f30c9aab0f16c96bf14f1208f0f303c1784']}
    },
    'PCE': {
        'ea13cd7f6bc18265d13aa9ef6c86006f1d23a652d8b65fad54dd2b00d3073934': {
            'version': '0.4.0-pce.2', 'features': ['PLCH1'],
            'receipt_sha256': '7f2c849c9395b9cf7403bbc73331b7e3cc36a4c83cc2febd08afe3abe182ad3e',
            'from': ['219ce7f984f259b5329bdc16b4eac27a973191f89937ab5b311ebd72a51f68c7']}
    },
    'SFC': {
        'f2e34dba43992149e5a295e7577c8f58dff4fc994ae0b40fdf3f59cc75d0867d': {
            'version': '0.4.0-sfc.3', 'features': ['PLCH1'],
            'receipt_sha256': '1bd8e7fbc69a0cd3674ca822bd81c8e1146e15857251124d54e4117668759ccd',
            'from': ['c67971fc368f5183f2a80918692d82eff7ead90761c1f203e3a67c4642ecc79e',
                     '24306de872a9bab19d52b518940bfa18fd79eabbb0c76e9386302be52f35194b']},
        '24306de872a9bab19d52b518940bfa18fd79eabbb0c76e9386302be52f35194b': {
            'version': '0.4.0-sfc.2', 'features': ['PLCH1'],
            'hardware_rejected': 'Menu raster exceeds the APF refresh limit; black before menu on Pocket',
            'receipt_sha256': '3571d8fcb342ee4510bfaa20885b4a39706919e1df81a301a9cbbba1abd72b23',
            'from': ['c67971fc368f5183f2a80918692d82eff7ead90761c1f203e3a67c4642ecc79e']}
    },
    'CPS2': {
        '3df11ca2fe8919e78188c15acef891191e021bece266d267c959763b64ee228c': {
            'version': '0.4.0-cps2.3', 'features': [],
            'receipt_sha256': 'f56f57de6139ecc03428c893c17c7b01ebea16eb0a696bcc8062e91c8b4fd397',
            'from': ['baa9d00580ac6bd216a9a6af8627b11463c503bf8934b2a638f8cac437650651',
                     '1bf2efba4aec704faed20570a444ae8604b3055767007a930b2285e16dee3848',
                     '9b02d9deaa37ed4312c18259dcacc289e462d092c7e411ff4e44a85cfba3fb03',
                     '5f52732fb8ebe51e0f5cc7c8c2e424535cc32939edd564908224381ac6680e20']},
        '5f52732fb8ebe51e0f5cc7c8c2e424535cc32939edd564908224381ac6680e20': {
            'version': '0.4.0-cps2.3', 'features': [],
            'validation_rejected': 'Intermediate build inherits the reproduced native EEPROM ERASE_ALL initialization defect',
            'receipt_sha256': '1470194213435c2322907a502d8dd09aea336c9d04815080db8333400f2de999',
            'from': ['baa9d00580ac6bd216a9a6af8627b11463c503bf8934b2a638f8cac437650651',
                     '1bf2efba4aec704faed20570a444ae8604b3055767007a930b2285e16dee3848',
                     '9b02d9deaa37ed4312c18259dcacc289e462d092c7e411ff4e44a85cfba3fb03']},
        '9b02d9deaa37ed4312c18259dcacc289e462d092c7e411ff4e44a85cfba3fb03': {
            'version': '0.4.0-cps2.2', 'features': [],
            'validation_rejected': 'Native SPI parameter/NVRAM read latency and per-game configuration fail protocol validation',
            'receipt_sha256': 'c7303fb5f99123902f35ec98620026fa00caa11d26fdc70afdc05256e342c16e',
            'from': ['baa9d00580ac6bd216a9a6af8627b11463c503bf8934b2a638f8cac437650651',
                     '1bf2efba4aec704faed20570a444ae8604b3055767007a930b2285e16dee3848']},
        '1bf2efba4aec704faed20570a444ae8604b3055767007a930b2285e16dee3848': {
            'version': '0.4.0-cps2.1', 'features': [],
            'hardware_rejected': 'Pocket reported black before menu; do not reinstall this candidate',
            'receipt_sha256': '25f09b1b795889e9e3abc6dc27fad3899aa50ef3ab6ef843ce6ef745b5fa9a39',
            'from': ['baa9d00580ac6bd216a9a6af8627b11463c503bf8934b2a638f8cac437650651']}
    },
}


def validate(package, system):
    package = Path(package)
    short, _, platform = delivery.PROFILES[system]
    core = package/'core'/('Cores/pocketlab.'+short)
    digest = delivery.sha(core/(platform+'.rbf_r'))
    candidate = CATALOG.get(system, {}).get(digest)
    if not candidate:
        raise ValueError('Native feature candidate is not in the reviewed artifact registry')
    if candidate.get('hardware_rejected'):
        raise ValueError('Candidate rejected after hardware feedback: '+candidate['hardware_rejected'])
    if candidate.get('validation_rejected'):
        raise ValueError('Candidate rejected after protocol validation: '+candidate['validation_rejected'])
    if delivery.sha(package/'build-receipt.json') != candidate['receipt_sha256']:
        raise ValueError('Candidate receipt is not the independently reviewed build receipt')
    receipt = delivery.read(package/'build-receipt.json')
    metadata = check_core(core)
    if (receipt['bitstream_sha256'] != digest or receipt['version'] != candidate['version']
            or receipt['features'] != candidate['features'] or receipt['minimum_slack_ns'] < 0
            or receipt['timing_records'] < 40 or metadata['metadata']['version'] != candidate['version']):
        raise ValueError('Native feature candidate receipt differs')
    for row in receipt['files']:
        delivery.check_record(package/'core', row, system)
    for rel, expected in receipt['source_inputs'].items():
        if delivery.sha(delivery.safe_path(package/'sources', rel)) != expected:
            raise ValueError('Candidate corresponding source differs: '+rel)
    return digest, candidate


def upgrade(card, package, changes, core_prefix, system, out):
    """Retain user display/input choices, ordinary progress and namespace bindings."""
    card, package, out = map(Path, (card, package, out))
    digest, candidate = validate(package, system)
    source = package/'core'
    current = check_core(card/core_prefix)
    wanted = check_core(source/core_prefix)
    if current['cores'] != wanted['cores'] or current['metadata']['platform_ids'] != wanted['metadata']['platform_ids']:
        raise ValueError('Candidate changes the native core identity')
    binary = core_prefix+current['cores'][0]['filename']
    if delivery.sha(delivery.safe_path(card, binary)) not in candidate['from']:
        raise ValueError('Candidate upgrade requires an explicitly supported previous native binary')
    old_data = delivery.read(card/core_prefix/'data.json')
    new_data = delivery.read(source/core_prefix/'data.json')
    previous_slots = old_data['data']['data_slots']
    new_slots = new_data['data']['data_slots']
    if new_slots[:len(previous_slots)] != previous_slots:
        raise ValueError('Candidate changes an existing data-slot binding')
    video = delivery.read(card/core_prefix/'video.json')
    new_video = delivery.read(source/core_prefix/'video.json')
    if video['video']['scaler_modes'] != new_video['video']['scaler_modes']:
        raise ValueError('Candidate changes existing display geometry')
    def mode_id(mode):
        return int(mode['id'], 0) if isinstance(mode['id'], str) else mode['id']
    identifiers = {mode_id(m) for m in video['video'].get('display_modes', [])}
    video['video'].setdefault('display_modes', []).extend(m for m in new_video['video'].get('display_modes', [])
                                                         if mode_id(m) not in identifiers)
    current['metadata'].update(version=wanted['metadata']['version'], date_release=wanted['metadata']['date_release'])
    overrides = {'core.json': {'core': current}, 'video.json': video, 'data.json': new_data}
    for name, value in overrides.items():
        delivery.write(out/core_prefix/name, value)
    selected = []
    guards = []
    for path in (card/core_prefix).iterdir():
        if path.is_file():
            rel = path.relative_to(card).as_posix()
            guards.append(delivery.snapshot(delivery.safe_path(card, rel), rel))
    # Ensure the three merged definitions are considered even when candidate and current bytes matched.
    changes = [c for c in changes if c['path'] not in {core_prefix+n for n in overrides}]
    changes += [{**delivery.snapshot(out/core_prefix/n, core_prefix+n), 'source': str(out)} for n in overrides]
    for row in changes:
        rel = row['path']
        target = delivery.allowed(card, rel, system)
        previous = delivery.digest(target)
        if rel.startswith(core_prefix) and Path(rel).name not in (*overrides, Path(binary).name):
            continue
        if rel.startswith('Platforms/') and previous is not None:
            continue
        if rel.startswith('Saves/') and previous is not None:
            continue
        if previous != row['sha256']:
            selected.append({**row, 'previous_sha256': previous})
        elif previous is not None:
            guards.append(delivery.snapshot(target, rel))
    return {'changes': selected, 'guards': guards, 'operation': 'reviewed_native_feature_upgrade'}
