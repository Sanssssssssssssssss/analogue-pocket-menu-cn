#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the existing GBA save/lifecycle adversarial bench with the F2 controller.

The APF host is simulated; no game CPU, card, save durability or UI renderer is
emulated here. The actual shared raster is compared in probe_view.py.
"""
import argparse,hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'experiments/gba_menu'
sys.path.insert(0,str(OLD))
from prepare_test import prepare as old_fixtures
spec=importlib.util.spec_from_file_location('coverflow_pack',Path(__file__).with_name('library.py'))
pack=importlib.util.module_from_spec(spec);spec.loader.exec_module(pack)
spec=importlib.util.spec_from_file_location('gba_base',OLD/'prepare_build.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
replace=base.replace

def bench(fault_recovery=False):
    s=(OLD/'tb_menu.sv').read_text(encoding='utf8')
    s=replace(s,'reg [31:0] capacity=65536;','''reg [31:0] capacity=65536;
    wire cf_menu,cf_go,cf_direction,cf_invalidate,cf_commit;
    wire [3:0] cf_target,cf_title_target;
    reg [3:0] cf_level=0,cf_title_level=0;
    reg cf_want=0;
    integer art_chunks=0,art_bytes=0;
    reg [31:0] art_origin=0;
    integer anim_left=0;
    integer cf_divider=0;
    reg cf_frame=0;
    wire cf_anim=anim_left!=0;
    always @(negedge clk)begin
        cf_divider=(cf_divider+1)%16;cf_frame=cf_divider==0;
        if(cf_go)anim_left=128;
        else if(anim_left>0)anim_left=anim_left-1;
        if(cf_frame)begin
            if(!cf_menu)cf_level=0;
            else if(cf_level<cf_target)cf_level=cf_level+1;
            else if(cf_level>cf_target)cf_level=cf_level-1;
            if(cf_title_level<cf_title_target)cf_title_level=cf_title_level+1;
            else if(cf_title_level>cf_title_target)cf_title_level=cf_title_level-1;
        end
    end''')
    s=replace(s,'.frame_request(req)', '''.cf_want_art(cf_want),.cf_wanted_game(11'd0),.cf_anim(cf_anim),.cf_frame_tick(cf_frame),
        .cf_mem_idle(1'b1),.cf_fetch_fault(1'b0),.cf_upload_ready(1'b1),.cf_level(cf_level),.cf_title_level(cf_title_level),
        .cf_menu(cf_menu),.cf_go(cf_go),.cf_direction(cf_direction),.cf_invalidate(cf_invalidate),.cf_commit(cf_commit),
        .cf_level_target(cf_target),.cf_title_target(cf_title_target),
        .frame_request(req)''')
    s=replace(s,'if(slot==100 && (address[31:28]==6 || address[31:28]==7))begin', '''if(slot==100 && address==32'h71000000)begin
                        if(length!=2048 || !cf_menu || bound || cf_title_level!=0)$fatal(1,"unsafe Unicode map transfer");
                    end else if(slot==100 && address>=32'h42000000 && address<32'h42800000)begin
                        if(!rst || bound || !cf_menu || address!=32'h42000000+art_bytes)$fatal(1,"unsafe art transfer");
                        if(art_bytes==0)art_origin=off;
                        if(off!=art_origin+art_bytes || length!=(art_chunks==2 ? 12800:16384))$fatal(1,"art layout/chunk mismatch");
                        art_bytes=art_bytes+length;art_chunks=art_chunks+1;
                    end else if(slot==100 && (address[31:28]==6 || address[31:28]==7))begin''')
    s=replace(s,'if(ticks%16==0)visible=fault || (owned && show) || (!owned && bound);',
        'if(ticks%16==0)visible=cf_menu ? cf_level!=0:fault || (owned && show) || (!owned && bound);')
    s=replace(s,'#100;ready=1;menu(0);', '''#100;ready=1;menu(0);
        cf_want=1;wait(cf_commit);cf_want=0;repeat(4)@(negedge clk);
        if(art_chunks!=3 || art_bytes!=45568)$fatal(1,"incomplete atlas upload");
        // Idle longer than TIMEOUT: entering a fade must start a new watchdog.
        repeat(6100)@(negedge clk);''')
    s=replace(s,'PASS: boot/paint ownership recovery, Stop/Run reset, first-fault retention; bounded frames, A/B, three launches, 64K/128K, pause, save+RTC+flush, path rejection and timeout',
        'PASS: F2 bounded atlas/text transfer, idle-to-fade, A/B/wrap, Stop/Run, three ROM launches, 64K/128K ordinary saves, RTC, pause/resume, failed-flush progress retention, save-path rejection and stale-done timeout')
    s=replace(s,'begin wait(state==13 && selected==selection && visible);repeat(2)@(negedge clk);end',
        '''begin $display("wait menu page=%0d selection=%0d",page,selection);
            wait(state==13 && selected==selection && visible);repeat(2)@(negedge clk);
            $display("menu ready page=%0d selection=%0d",page,selection);end''')
    s=replace(s,'watchdog state=%0d code=%h page=%0d selected=%0d",state,code,page,selected',
        'watchdog state=%0d code=%h page=%0d selected=%0d cfmenu=%b level=%d target=%d art=%0d want=%b pending=%h",state,code,page,selected,cf_menu,cf_level,cf_target,art_chunks,cf_want,dut.cf_pending')
    if fault_recovery:
        s=replace(s,".SETTLE_CYCLES(20'd16)",".SETTLE_CYCLES(20'd16),.FRAME_TIMEOUT(34'd256)")
        s=replace(s,'reg cf_want=0;', '''reg cf_want=0,cf_fault=0,cf_uploaded=1;
    reg [2:0] cf_art_result=0;
    integer fail_remaining=0,art_attempts=0;''')
        s=replace(s,".cf_fetch_fault(1'b0),.cf_upload_ready(1'b1)",
            '.cf_fetch_fault(cf_fault),.cf_upload_ready(cf_uploaded)')
        s=replace(s,'reply(0);\n                end else if(wr)',
            "reply(slot==100 && address[31:24]==8'h42 ? cf_art_result:3'd0);\n                end else if(wr)")
        s=replace(s,"if(!rst || bound || !cf_menu || address!=32'h42000000+art_bytes)",'''if(address==32'h42000000)begin
                            art_attempts=art_attempts+1;art_bytes=0;art_chunks=0;
                            cf_art_result=fail_remaining>0 ? 3'd2:3'd0;
                            if(fail_remaining>0)fail_remaining=fail_remaining-1;
                        end
                        if(!rst || bound || !cf_menu || address!=32'h42000000+art_bytes)''')
        s=replace(s,'cf_want=1;wait(cf_commit);cf_want=0;repeat(4)@(negedge clk);', '''
        fail_remaining=1;cf_want=1;
        wait(cf_commit);cf_want=0;repeat(4)@(negedge clk);
        if(art_attempts!=2 || dut.cf_art_unavailable || fault || art_bytes!=45568)
            $fatal(1,"transient APF failure did not recover automatically");
        $display("PASS: transient APF failure reloads a complete cover without Stop/Run");
        ready=0;repeat(8)@(negedge clk);ready=1;menu(0);
        art_attempts=0;fail_remaining=10;cf_want=1;
        wait(art_attempts==3 && dut.cf_art_unavailable && state==13);
        repeat(7000)@(negedge clk);
        if(art_attempts!=3 || fault)$fatal(1,"persistent read error retries forever");
        cf_want=0;
        press(4);menu(0);if(page!=1 || dut.cf_art_unavailable)$fatal(1,"page did not restore recovery budget");
        press(5);menu(0);if(page!=0)$fatal(1,"cannot return after persistent error");
        $display("PASS: persistent failure stops after two retries and preserves A/B navigation");
        art_attempts=0;fail_remaining=0;cf_uploaded=0;cf_want=1;
        wait(state==51);cf_fault=1;
        wait(cf_invalidate);@(negedge clk);cf_fault=0;cf_uploaded=1;
        wait(cf_commit);cf_want=0;repeat(4)@(negedge clk);
        if(art_attempts!=2 || fault)$fatal(1,"backend failure did not recover");
        $display("PASS: backend fault drains, invalidates and reloads");
        art_attempts=0;cf_uploaded=0;cf_want=1;
        wait(state==54);@(negedge clk);cf_uploaded=1;
        cf_want=1;wait(cf_commit);cf_want=0;repeat(4)@(negedge clk);
        if(art_attempts!=2 || fault)$fatal(1,"incomplete upload did not recover");
        $display("PASS: incomplete upload times out then reloads");''')
        s=replace(s,'        // A malformed progress path is rejected before opening a ROM or save.', '''
        art_chunks=0;art_bytes=0;fail_remaining=1;cf_want=1;
        wait(art_chunks==1);cf_want=0;
        wait(state==13 || fault);
        if(fault)$fatal(1,"cover error prevented selecting a game");
        press(4);running;
        if(transactions!=4 || save_reads!=2 || rtc_reads!=2)$fatal(1,"launch after cover error lost progress");
        quit_game;menu(0);
        $display("PASS: existing save and RTC load, game launch and save-return still work after a cover error");
        // A malformed progress path is rejected before opening a ROM or save.''')
        s=replace(s,"code!=8'h13||rom_reads!=3||bound", "code!=8'h13||rom_reads!=4||bound")
    return s

def run(build,out,fault_recovery=False):
    build,out=Path(build).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
    out.mkdir(parents=True)
    f1=old_fixtures(out/'f1');f2=out/'f2';pack.upgrade(f1/'library',f2)
    for name in ('root','games'):
        raw=(f1/(name+'.hex')).read_text().splitlines()
        previous=bytes(int(v,16) for v in raw)
        count=int.from_bytes(previous[8:12],'little')
        oldpath=(f1/'library'/ 'Assets/gbalab/common/menu.bin') if name=='root' else next((f1/'library/Assets/gbalab/common/libs').glob('*.bin'))
        newpath=f2/oldpath.relative_to(f1/'library');raw=newpath.read_bytes()[:64+count*1024]
        for i in range(count):
            if raw[64+i*1024+32:64+(i+1)*1024]!=previous[64+i*1024+32:64+(i+1)*1024]:raise AssertionError('Progress/path identity changed')
        (out/(name+'.hex')).write_text(''.join(f'{b:02x}\n' for b in raw))
    (out/'paths.vh').write_bytes((f1/'paths.vh').read_bytes())
    controller=build/'src/fpga/core/gba_menu.sv'
    text=bench(fault_recovery)
    if 'cf_wanted_slot' in controller.read_text(encoding='utf8'):
        text=replace(text,'.cf_wanted_game(11\'d0),',".cf_wanted_game(11'd0),.cf_wanted_slot(3'd0),")
    tb=out/'tb_menu.sv';tb.write_text(text,encoding='utf8')
    command=['iverilog','-g2012','-I',str(out),'-s','tb_menu','-o',str(out/'control.sim'),str(controller),str(tb)]
    r=subprocess.run(command,capture_output=True,text=True,timeout=60)
    (out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run(['vvp',str(out/'control.sim')],cwd=out,capture_output=True,text=True,timeout=60)
    (out/'simulation.log').write_text(r.stdout+r.stderr);print('\n'.join((r.stdout+r.stderr).splitlines()[-24:]));r.check_returncode()
    if 'PASS:' not in r.stdout:raise ValueError('No lifecycle pass marker')
    (out/'receipt.json').write_text(json.dumps({'result':'passed','scope':'Controller + simulated APF host and video state; synthetic ROM header bytes, no game CPU/card/hardware/save durability',
        'cover_fault_recovery':fault_recovery,
        'inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [controller,tb,Path(__file__),Path(__file__).with_name('library.py')]},
        'f2_path_identity':'byte-exact compared to F1 records'},indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True);p.add_argument('--out',required=True)
    p.add_argument('--fault-recovery',action='store_true',help='Inject failed cover transfers and check navigation and recovery')
    a=p.parse_args();run(a.build,a.out,a.fault_recovery)
