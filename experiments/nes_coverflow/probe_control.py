#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the actual NES CoverFlow controller with synthetic APF transactions."""
import argparse,hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('nes_control_prepare',Path(__file__).with_name('prepare.py'))
prepare_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare_module)
load,replace,ROOT,HERE=prepare_module.load,prepare_module.replace,prepare_module.ROOT,prepare_module.HERE
library=load('nes_coverflow_library',HERE/'library.py')
gba_probe=load('gba_lifecycle_probe',ROOT/'experiments/gba_coverflow/probe_control.py')


def bench():
    s=gba_probe.bench()
    s=replace(s,".cf_fetch_fault(1'b0),.cf_upload_ready(1'b1)",".cf_fetch_fault(1'b0)")
    s=replace(s,'gba_menu #(','nes_menu #(')
    s=s.replace('/Assets/gbalab/common/','/Assets/neslab/common/').replace('/Assets/gba/common/','/Assets/nes/common/').replace('.gba"','.nes"')
    s=replace(s,'reg [31:0] capacity=65536;','reg [31:0] capacity=262144;')
    s=replace(s,'.cf_want_art(cf_want),', ".cf_want_art(cf_want),.cf_wanted_slot(3'd2),.cf_upload_ready(art_bytes==45568),")
    s=s.replace("32'h42000000","32'h42020000").replace("32'h42800000","32'h42030000")
    s=replace(s,'end else if(slot==1)begin','end else if(slot==0)begin')
    s=replace(s,'length!=32768','length!=16400')
    s=replace(s,'capacity=bindings[1]=="/Assets/nes/common/Second.nes" ? 131072 : 65536;',
        'if(capacity!=262144)$fatal(1,"wrong NES save capacity");')
    s=replace(s,'add_file("/Assets/nes/common/First.nes",32768);add_file("/Assets/nes/common/Second.nes",32768);',
        '''add_file("/Assets/nes/common/First.nes",16400);add_file("/Assets/nes/common/Second.nes",16400);
        add_file(`FIRST_SAVE,262144);add_file(`SECOND_SAVE,262144);''')
    s=replace(s,'rom_reads!=1||save_reads!=0||rtc_reads!=0','rom_reads!=1||save_reads!=1||rtc_reads!=0')
    s=replace(s,'flushes!=2||rtc_writes!=1','flushes!=1||rtc_writes!=0')
    s=replace(s,'capacity!=131072','capacity!=262144')
    s=replace(s,'save_reads!=1||rtc_reads!=1||capacity!=65536','save_reads!=3||rtc_reads!=0||capacity!=262144')
    s=replace(s,'64K/128K ordinary saves, RTC,','three seeded 256K ordinary saves, no RTC traffic,')
    return s


def fixtures(out):
    home='/Assets/neslab/common/menu.bin';child='/Assets/neslab/common/libs/test.bin'
    entries=[]
    for i,name in enumerate(['First','Second']):
        tag=str(i+1)*20
        entries.append({'title':'测试游戏'+str(i+1),'folder':False,'rom':'/Assets/nes/common/'+name+'.nes','bytes':16400,
            'save':'/Saves/neslab/common/'+tag+'.sav','rtc':'/Saves/neslab/common/'+tag+'.rtc'})
    for name,rows in [('root',[library.folder(child,'测试分类'),library.folder(home,'返回首页')]),
        ('games',entries+[library.folder(home,'返回首页')])]:
        raw,_,_=library.pack(rows);raw=raw[:64+len(rows)*1024]
        (out/(name+'.hex')).write_text(''.join(f'{b:02x}\n' for b in raw))
    (out/'paths.vh').write_text('`define GAMES_PATH "'+child+'"\n'+
        '`define FIRST_SAVE "'+entries[0]['save']+'"\n'+
        '`define SECOND_SAVE "'+entries[1]['save']+'"\n')


def run(build,out):
    build,out=Path(build).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
    out.mkdir(parents=True);fixtures(out)
    tb=out/'tb_menu.sv';tb.write_text(bench(),encoding='utf8')
    controller=build/'target/pocket/nes_menu.sv'
    r=subprocess.run(['iverilog','-g2012','-I',str(out),'-s','tb_menu','-o',str(out/'control.sim'),str(controller),str(tb)],capture_output=True,text=True,timeout=60)
    (out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run(['vvp',str(out/'control.sim')],cwd=out,capture_output=True,text=True,timeout=60)
    (out/'simulation.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
    if 'PASS:' not in r.stdout:raise ValueError('No lifecycle pass marker')
    (out/'receipt.json').write_text(json.dumps({'result':'passed','scope':'Actual prepared NES controller, synthetic APF files and video/fade state; no game CPU/device/save durability',
        'cases':'F2 atlas physical mapping, Unicode widths, A/B/wrap, three native launches and seeded save reads, pause/resume, save/flush, failed-flush live-state retention, unsafe path and stale completion rejection, Stop/Run',
        'inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [controller,tb,Path(__file__),HERE/'library.py']}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();run(a.build,a.out)
