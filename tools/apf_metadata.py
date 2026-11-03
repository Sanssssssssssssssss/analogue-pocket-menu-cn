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
        'GBA CoverFlow .6 freezes after opening a child page on hardware; covers missing and input unresponsive'
}


def check_candidate_bitstream(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
    digest=h.hexdigest()
    if digest in REJECTED_CANDIDATES:
        raise ValueError('Device-rejected APF candidate: '+REJECTED_CANDIDATES[digest])
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
