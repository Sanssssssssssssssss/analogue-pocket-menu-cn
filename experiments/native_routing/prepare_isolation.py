#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare four minimal loader tests using the same reviewed, no-game FPGA hardware."""
import argparse
from pathlib import Path
from prepare_trial import trial

HERE=Path(__file__).resolve().parent
def prepare(archive,out):
    out=trial(archive,out)
    template=(HERE/'isolation_loader.asm').read_text(encoding='utf8')
    assert template.count('// BODY')==1
    for number in [4,5,6,7]:
        lines=[f'    ld r0,#{1 if number==7 else 0}','    core r0','    ld r0,#0','    loadf r0']
        if number==6:lines+=['    ld r0,#1','    core r0','    ld r0,#0','    loadf r0']
        if number in [5,6]:
            lines+=['    ld r0,#0x60000000','    pmpr r0,r9','    ld r0,#0x60000024','    pmpw r0,r9',f'    ld r8,#{0xB1 if number==5 else 0xB2}','    ld r0,#0x60000020','    pmpw r0,r8']
        folder=out/'isolation'/f'Route{number}';folder.mkdir(parents=True)
        (folder/'loader.asm').write_text(template.replace('// BODY','\n'.join(lines)),encoding='utf8',newline='\n')
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['archive','out']:p.add_argument('--'+name,required=True)
    a=p.parse_args();print(prepare(a.archive,a.out))
