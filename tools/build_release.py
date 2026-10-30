#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package the accepted bitstream with public metadata; exclude all user assets."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.1.2-public.1'
RBF_SHA='1cb62f954484be8c002e2f6c74e7813d34ef0cbe2fb910f3916dab1c43d766d9'

def create(bitstream,out):
    bitstream,out=Path(bitstream).resolve(),Path(out).resolve()
    if out.exists():raise ValueError('Release output must be a new directory')
    if hashlib.sha256(bitstream.read_bytes()).hexdigest()!=RBF_SHA:
        raise ValueError('Bitstream differs from the reviewed/device-tested 0.1.2 build')
    if bitstream.stat().st_size!=2097492:raise ValueError('Bitstream size mismatch')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    out.mkdir(parents=True)
    stage=out/'core'
    shutil.copytree(ROOT/'packaging',stage)
    shutil.copy2(bitstream,stage/'Cores/pocketlab.CoverFlow/gbc.rbf_r')
    files=[]
    for p in sorted(stage.rglob('*')):
        if p.is_file():files.append({'path':p.relative_to(stage).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    manifest={'version':VERSION,'bitstream_sha256':RBF_SHA,'source_commit':commit,
              'source_url':'https://github.com/Sanssssssssssssssss/analogue-pocket-menu-cn',
              'hardware_scope':'User confirmed Chinese menus, GB/GBC launch and folder flash fix; not all games/save features',
              'files':files}
    (stage/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    archive=out/f'analogue-pocket-menu-cn-{VERSION}-core.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(stage.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(stage).as_posix())
        z.write(ROOT/'LICENSE.md','LICENSE.md')
        z.write(ROOT/'docs/INSTALL.zh-CN.md','INSTALL.zh-CN.md')
        for p in sorted((ROOT/'LICENSES').glob('*.txt')):z.write(p,'LICENSES/'+p.name)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (out/'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n',encoding='ascii')
    return archive

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bitstream',required=True);p.add_argument('--out',required=True)
    a=p.parse_args()
    try:print(create(a.bitstream,a.out))
    except (OSError,ValueError) as e:p.exit(2,str(e)+'\n')
