#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check generated practical profiles through the actual native cheat parser."""
import argparse,hashlib,json,subprocess,zlib
from pathlib import Path
from library import cheat_payload,ROOT


def run(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
    out.mkdir(parents=True);raw=b'\x11'*32768
    profile={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'sha1':hashlib.sha1(raw).hexdigest(),'crc32':f'{zlib.crc32(raw)&0xffffffff:08x}',
        'effects':[{'title':'测试辅助一','codes':[{'type':'par','address':0xc123,'value':0x7f},{'type':'game_genie','code':'058-BA8-E66'}]},
            {'title':'测试辅助二','codes':[{'type':'game_genie','code':'055-BA8'}]}]}
    payload=out/'synthetic.cht';payload.write_bytes(cheat_payload(profile,raw))
    parser=source/'rtl/gg/cheat_loader.sv';bench=source/'tools/sim/tb_cheat_loader.sv'
    r=subprocess.run(['iverilog','-g2012','-s','tb_cheat_loader','-o',str(out/'parser.sim'),str(parser),str(bench)],capture_output=True,text=True,timeout=60)
    (out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run(['vvp',str(out/'parser.sim'),'+f='+str(payload)],capture_output=True,text=True,timeout=60)
    (out/'simulation.log').write_text(r.stdout+r.stderr);r.check_returncode()
    decoded=[]
    for line in r.stdout.splitlines():
        fields=line.split()
        if fields[:2]==['PUSH','P']:decoded.append(('P',*(int(v,16) for v in fields[2:4]),int(fields[4])))
        elif fields[:2]==['PUSH','G']:decoded.append(('G',*(int(v,16) for v in fields[2:5]),int(fields[5])))
    expected=[('P',0x123,0x7f,0),('G',0x78ba,5,3,1),('G',0x75ba,5,0,0)]
    if decoded!=expected:raise ValueError('Generated profile differs from real native parser: '+str(decoded))
    result={'result':'passed','scope':'Two synthetic practical effects, mixed PAR and six/nine-digit Game Genie, actual upstream parser and monitor; no game execution or real ROM payload',
        'decoded':decoded,'inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [parser,bench,Path(__file__).with_name('library.py'),payload]}}
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS: generated version-bound profiles preserve all three code semantics through the real native parser')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();run(a.source,a.out)
