#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check APF identity before packaging or installing a core."""
import json
from pathlib import Path


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
    for item in core['cores']:
        name = item['filename']
        if len(name)>15 or Path(name).name!=name or not (folder/name).is_file():
            raise ValueError('Invalid or missing APF bitstream: '+name)
    return core
