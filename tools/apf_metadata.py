#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check APF identity before packaging or installing a core."""
import hashlib
import json
from pathlib import Path

REQUIRED_JSON=('core.json','audio.json','data.json','input.json','interact.json','variants.json','video.json')
# Device-reported failures must not be republished just because fit/tests passed.
REJECTED_CANDIDATES={
    '5f8f36f9414f7efc056d8c9aedf59fe1eced262ef50a37eb1315b79c7c15fb84':
        'GBA CoverFlow .5 returned operation failed on hardware; accepted .3 was restored',
    '67b91aab041bdab26443bed34e856124fdaf50ec4f689afe5765aceaf3cf6a4d':
        'GBA CoverFlow .6 freezes after opening a child page on hardware; covers missing and input unresponsive',
    'd1d17a0c19216bf549cb07708e93bc5a7730c897e1d7df34ccd7427b2a8b13dc':
        'GBA CoverFlow .7 intermittently reports operation failed during use on hardware',
    '24306de872a9bab19d52b518940bfa18fd79eabbb0c76e9386302be52f35194b':
        'SNES CoverFlow .2 is black before the menu; menu refresh exceeds the APF video limit',
    '1bf2efba4aec704faed20570a444ae8604b3055767007a930b2285e16dee3848':
        'CPS2 CoverFlow .1 is black before the menu on hardware',
}
VALIDATION_REJECTED_CANDIDATES={
    'df5c40d7c78904510516fb93c19834e521fb008be9453053220472fdd3f4f66f':
        'CPS1 intermediate build inherits the reproduced native EEPROM ERASE_ALL initialization defect',
    '02c532fe66f8db2016cfcf085265bde7351c6ef9cfb8cfc61c5480230a742ad2':
        'CPS1.5 intermediate build inherits the reproduced native EEPROM ERASE_ALL initialization defect',
    '5f52732fb8ebe51e0f5cc7c8c2e424535cc32939edd564908224381ac6680e20':
        'CPS2 intermediate .3 inherits the reproduced native EEPROM ERASE_ALL initialization defect',
    '9b02d9deaa37ed4312c18259dcacc289e462d092c7e411ff4e44a85cfba3fb03':
        'CPS2 .2 fails native SPI parameter/NVRAM readback and per-game configuration in protocol simulation',
}


def check_candidate_bitstream(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
    digest=h.hexdigest()
    if digest in REJECTED_CANDIDATES:
        raise ValueError('Device-rejected APF candidate: '+REJECTED_CANDIDATES[digest])
    if digest in VALIDATION_REJECTED_CANDIDATES:
        raise ValueError('Validation-rejected APF candidate: '+VALIDATION_REJECTED_CANDIDATES[digest])
    return digest


def check_core(folder):
    folder = Path(folder)
    core = json.loads((folder/'core.json').read_text(encoding='utf-8'))['core']
    metadata = core['metadata']
    expected = metadata['author']+'.'+metadata['shortname']
    if folder.name != expected:
        raise ValueError(f'APF folder identity mismatch: {folder.name} != {expected}')
    for key, limit in [('shortname',31),('author',31),('description',63),('url',63),('version',31),('date_release',10)]:
        if len(metadata[key].encode('utf-8')) > limit:
            raise ValueError('APF metadata too long: '+key)
    # All seven definitions are mandatory, including an empty variants list.
    # https://www.analogue.co/developer/docs/openfpga/core-definition-files
    for filename in REQUIRED_JSON:
        path=folder/filename
        if not path.is_file():raise ValueError('Missing required APF definition: '+filename)
        document=json.loads(path.read_text(encoding='utf-8-sig'))
        value=document.get(path.stem) if isinstance(document,dict) else None
        if not isinstance(value,dict) or value.get('magic')!='APF_VER_1':
            raise ValueError('Invalid APF definition: '+filename)
        if filename=='variants.json' and not isinstance(value.get('variant_list'),list):
            raise ValueError('Invalid APF variants.json variant_list')
    for item in core['cores']:
        name = item['filename']
        if len(name)>15 or Path(name).name!=name or not (folder/name).is_file():
            raise ValueError('Invalid or missing APF bitstream: '+name)
    return core
