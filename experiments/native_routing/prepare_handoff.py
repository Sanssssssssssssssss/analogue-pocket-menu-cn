#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare measured input and documented OS-reload controls, retaining accepted hardware."""
import argparse
from pathlib import Path
import shutil
from prepare_isolation import prepare

HERE=Path(__file__).resolve().parent

def handoff(archive,reuse,out):
    out=Path(out).resolve()
    if reuse:
        source=Path(reuse).resolve()
        if out.exists() or not all(p.is_relative_to(HERE.parents[1]/'.work') for p in [source,out]):
            raise ValueError('Reuse and fresh output must be in checkout .work')
        out.mkdir(parents=True)
        for name in ['A','B','loaders','isolation']:shutil.copytree(source/name,out/name)
        for mode,host in [('pre-init',0),('reset-exit',0x4001),('full-init',0x4002)]:
            expected=(HERE/'loader.asm').read_text().replace('constant early_host = 0',f'constant early_host = {host}')
            assert (out/'loaders'/mode/'loader.asm').read_text()==expected,'Stale reused loader source'
    else:out=prepare(archive,out)
    template=(HERE/'isolation_loader.asm').read_text(encoding='utf8')
    for number,name in [(11,'timing_body.asm'),(12,'reentry_body.asm')]:
        folder=out/'handoff'/f'Route{number}';folder.mkdir(parents=True)
        (folder/'loader.asm').write_text(template.replace('// BODY',(HERE/name).read_text()),encoding='utf8',newline='\n')
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--archive');g.add_argument('--reuse');p.add_argument('--out',required=True)
    a=p.parse_args();print(handoff(a.archive,a.reuse,a.out))
