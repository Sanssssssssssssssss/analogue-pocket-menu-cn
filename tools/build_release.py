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
from display_styles import configure as configure_display

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.1.2-public.1'
RBF_SHA='1cb62f954484be8c002e2f6c74e7813d34ef0cbe2fb910f3916dab1c43d766d9'

def create(bitstream,out,display_profile=False):
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
    version=VERSION
    if display_profile:
        version='0.1.2-display.1';folder=stage/'Cores/pocketlab.CoverFlow'
        meta=json.loads((folder/'core.json').read_text(encoding='utf8'));meta['core']['metadata']['version']=version
        # Official equivalent of the retained bit31 flag, also understood by
        # older community metadata validators. Physical cart power stays off.
        meta['core']['framework']['hardware']['cartridge_adapter']=-1
        (folder/'core.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf8')
        video=json.loads((folder/'video.json').read_text(encoding='utf8'))
        (folder/'video.json').write_text(json.dumps(configure_display(video,'gbc'),indent=2)+'\n',encoding='utf8')
    files=[]
    for p in sorted(stage.rglob('*')):
        if p.is_file():files.append({'path':p.relative_to(stage).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    manifest={'version':version,'bitstream_sha256':RBF_SHA,'source_commit':commit,
              'source_url':'https://github.com/Sanssssssssssssssss/analogue-pocket-menu-cn',
              'hardware_scope':'User confirmed Chinese menus, GB/GBC launch and folder flash fix; not all games/save features',
              'files':files}
    if display_profile:manifest['display_profile']='Optional native color LCD/CRT modes and sharpness only; accepted bitstream unchanged; physical mode appearance pending'
    (stage/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    archive=out/f'analogue-pocket-menu-cn-{version}-core.zip'
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
    p.add_argument('--display-profile',action='store_true',help='Separate metadata-only display candidate; accepted bitstream stays unchanged')
    a=p.parse_args()
    try:print(create(a.bitstream,a.out,a.display_profile))
    except (OSError,ValueError) as e:p.exit(2,str(e)+'\n')
