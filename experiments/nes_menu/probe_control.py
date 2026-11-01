#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the adapted NES lifecycle using the retained GBA lifecycle harness."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from prepare_build import controller
from library import ASSETS,SAVES,pack
ROOT=Path(__file__).resolve().parents[2]

def run(out):
    out=Path(out).resolve();assert not out.exists() and out.is_relative_to(ROOT/'.work');out.mkdir(parents=True)
    (out/'nes_menu.sv').write_text(controller(),encoding='utf8')
    home='/'+ASSETS+'/menu.bin';child='/'+ASSETS+'/libs/test.bin'
    def entry(title,rom,folder,tag='0'):
        return {'title':title,'rom':rom,'folder':folder,'bytes':32768,
                'save':f'/{SAVES}/{tag*20}.sav','rtc':f'/{SAVES}/{tag*20}.rtc'}
    first=entry('测试一','/Assets/nes/common/First.nes',False,'1')
    second=entry('测试二','/Assets/nes/common/Second.nes',False,'2')
    for name,entries in [('root',[entry('红白机',child,True),entry('返回首页',home,True)]),
                         ('games',[first,second,entry('返回首页',home,True)])]:
        raw=pack(entries);raw=raw[:64+len(entries)*1024]
        (out/(name+'.hex')).write_text(''.join(f'{b:02x}\n' for b in raw))
    (out/'paths.vh').write_text(f'`define GAMES_PATH "{child}"\n')
    tb=(ROOT/'experiments/gba_menu/tb_menu.sv').read_text(encoding='utf8')
    tb=tb.replace('gba_menu #','nes_menu #').replace('gbalab','neslab').replace('/Assets/gba/','/Assets/nes/').replace('.gba','.nes')
    tb=tb.replace('capacity=65536','capacity=262144').replace('slot==1)','slot==0)')
    tb=tb.replace('capacity=bindings[1]=="/Assets/nes/common/Second.nes" ? 131072 : 65536;','capacity=262144;')
    tb=tb.replace('save_reads!=0','save_reads!=1').replace('flushes!=2||rtc_writes!=1','flushes!=1||rtc_writes!=0')
    tb=tb.replace('capacity!=131072','capacity!=262144').replace('save_reads!=1||rtc_reads!=1||capacity!=65536','save_reads!=3||rtc_reads!=0||capacity!=262144')
    anchor='        #100;ready=1;menu(0);'
    assert anchor in tb
    tb=tb.replace(anchor,f'        add_file("{first["save"]}",262144);add_file("{second["save"]}",262144);\n'+anchor)
    tb=tb.replace('64K/128K, pause, save+RTC+flush','256K seeded progress, pause, save+flush without RTC')
    (out/'tb_menu.sv').write_text(tb,encoding='utf8')
    inputs=[out/'nes_menu.sv',out/'tb_menu.sv']
    r=subprocess.run(['iverilog','-g2012','-I',str(out),'-s','tb_menu','-o',str(out/'menu.sim'),*map(str,inputs)],capture_output=True,text=True)
    (out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run(['vvp',str(out/'menu.sim')],cwd=out,capture_output=True,text=True,timeout=90)
    (out/'simulation.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
    assert 'PASS:' in r.stdout
    receipt={'scope':'Adapted menu lifecycle with host/frame-ready/loader models; no NES CPU, physical RAM or SD',
             'result':'passed','checks':['three launches','seeded isolated saves','save/flush failure retains live game',
             'no RTC operations','A/B return','path rejection','stale completion timeout','Stop/Run reset'],
             'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();run(a.out)
