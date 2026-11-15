#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate release metadata, public inputs and tracked-file hygiene."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from build_release import VERSION
from build_library import FONT_SHA

ROOT=Path(__file__).resolve().parents[1]

def check():
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    names=[name for name in names if name]
    if not names:raise ValueError('No tracked files; stage the intended source tree first')
    forbidden={'.gb','.gbc','.gba','.nes','.sfc','.smc','.rtc','.state','.sav','.srm','.sus','.iso','.rbf','.rbf_r','.rev','.zip','.tar'}
    for name in names:
        p=ROOT/name
        if p.suffix.lower() in forbidden or any(part in ('.work','.build','dist','node_modules') for part in p.relative_to(ROOT).parts):
            raise ValueError(f'Private/generated data tracked: {name}')
        if re.search(r'(bios|bootrom).*\.bin$',name,re.I):raise ValueError(f'BIOS tracked: {name}')
        raw=p.read_bytes()
        if re.search(rb'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----',raw):
            raise ValueError(f'Credential pattern in {name}')
    meta=json.loads((ROOT/'packaging/Cores/pocketlab.CoverFlow/core.json').read_text(encoding='utf-8'))['core']
    assert meta['metadata']['version']==VERSION
    assert meta['metadata']['platform_ids']==['gbclab','gb','gbc']
    assert len(meta['metadata']['url'].encode())<=63
    assert meta['framework']['hardware']['cartridge_adapter']=='0x80000000'
    assert meta['cores'][0]['filename']=='gbc.rbf_r'
    slots=json.loads((ROOT/'packaging/Cores/pocketlab.CoverFlow/data.json').read_text(encoding='utf-8'))['data']['data_slots']
    assert any(s['id']==4 and s['required'] and s['size_exact']==2304 for s in slots)
    font=ROOT/'assets/fonts/unifont-18.0.01.hex.gz'
    assert hashlib.sha256(font.read_bytes()).hexdigest()==FONT_SHA
    inputs=json.loads((ROOT/'docs/build/source-inputs.json').read_text(encoding='utf-8'))['files']
    for item in inputs:
        assert hashlib.sha256((ROOT/'core/src'/item['path']).read_bytes()).hexdigest()==item['sha256'],item['path']
    docs=[ROOT/'README.md',ROOT/'README.en.md',ROOT/'LICENSE.md',ROOT/'CONTRIBUTING.md',*list((ROOT/'docs').glob('*.md'))]
    for doc in docs:
        content=doc.read_text(encoding='utf-8')
        for link in re.findall(r'\]\(([^)]+)\)',content):
            if re.match(r'^[a-zA-Z]+:|^#',link):continue
            target=(doc.parent/link.split('#')[0]).resolve()
            assert target.is_file(),f'Broken local link in {doc.name}: {link}'
    print(f'PASS: {len(names)} tracked files; {len(inputs)} hardware inputs; metadata/font/docs checked')

if __name__=='__main__':check()
