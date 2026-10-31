#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
from pathlib import Path
import argparse

from library import build,ASSETS
from test_library import rom

def prepare(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    card=out/'synthetic-card';base=card/'Assets/gba/common';base.mkdir(parents=True)
    (base/'First.gba').write_bytes(rom())
    (base/'Second.gba').write_bytes(rom(True))
    build(card,out/'library')
    root=out/'library'/ASSETS/'menu.bin'
    child=next((out/'library'/ASSETS/'libs').glob('*.bin'))
    for name,file in (('root',root),('games',child)):
        raw=file.read_bytes()
        # Header/records only: no game CPU or commercial payload.
        count=int.from_bytes(raw[8:12],'little');raw=raw[:64+count*1024]
        (out/(name+'.hex')).write_text(''.join(f'{b:02x}\n' for b in raw))
        if name=='games':game_path='/'+file.relative_to(out/'library').as_posix()
    (out/'paths.vh').write_text('`define GAMES_PATH "'+game_path+'"\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();print(prepare(a.out))
