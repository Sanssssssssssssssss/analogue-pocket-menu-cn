#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Download pinned upstream source archives into a fresh, local experiment folder."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile
from launch_plan import PROFILES

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);a=p.parse_args()
out=Path(a.out).resolve()
root=Path(__file__).resolve().parents[2]
if out.exists() or not out.is_relative_to(root/'.work'):
    raise ValueError('Output must be a new directory inside this checkout/.work')
out.mkdir(parents=True);originals=out/'originals';originals.mkdir()
records=[]
for platform,profile in PROFILES.items():
    url=f'https://codeload.github.com/{profile["repository"]}/zip/{profile["commit"]}'
    with urllib.request.urlopen(url,timeout=60) as response:raw=response.read(40*1024*1024+1)
    if len(raw)>40*1024*1024 or hashlib.sha256(raw).hexdigest()!=profile['archive_sha256']:
        raise ValueError(f'Unexpected upstream archive: {platform}')
    (originals/(platform+'.zip')).write_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if sum(x.file_size for x in z.infolist())>300*1024*1024:raise ValueError('Archive too large')
        prefix=z.namelist()[0].split('/')[0]+'/'
        for item in z.infolist():
            if not item.filename.startswith(prefix):raise ValueError('Unexpected archive root')
            rel=item.filename[len(prefix):]
            if not rel:continue
            parts=PurePosixPath(rel).parts
            if '..' in parts or '\\' in rel or ':' in rel or rel.startswith('/'):
                raise ValueError('Unsafe archive path')
            if (item.external_attr>>16)&0o170000==0o120000:raise ValueError('Archive link rejected')
            target=out/platform/rel
            if item.is_dir():target.mkdir(parents=True,exist_ok=True)
            else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(item))
    records.append({'platform':platform,'url':url,'sha256':profile['archive_sha256']})
(out/'sources.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps({'frozen_sources':[r['platform'] for r in records]}))
