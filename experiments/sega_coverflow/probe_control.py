#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise Sega launch/save/cheat sequencing with the real upstream parser."""
import argparse,hashlib,json,re,struct,subprocess
from pathlib import Path
from controller import load,replace,PROFILES,ROOT
HERE=Path(__file__).resolve().parent
nes_probe=load('sega_nes_probe',ROOT/'experiments/nes_coverflow/probe_control.py')


def bench(platform,case):
    namespace,slot,rom_address,mode=PROFILES[platform]
    s=nes_probe.bench().replace('nes_menu #(','sega_menu #(')
    s=s.replace('neslab',namespace).replace('/Assets/nes/','/Assets/'+platform+'/').replace('.nes"','.'+('sg' if platform=='sg1000' else platform)+'"')
    s=s.replace('262144','32768').replace('16400','32768')
    s=replace(s,".cf_wanted_slot(3'd2),",'')
    s=replace(s,'.cf_upload_ready(art_bytes==45568),',
        '.cf_upload_ready(art_bytes==45568),.cheat_loading(cheat_loading),.cheat_armed(cheat_armed),.cheat_payload_ready((genie_total!=0 || poke_total!=0) && !cheat_overrun),.cheat_parse_fault(cheat_overrun),')
    s=s.replace("32'h42020000","32'h42000000").replace("32'h42030000","32'h42010000")
    s=replace(s,'end else if(slot==0)begin',f'end else if(slot=={slot})begin')
    s=replace(s,"address!=32'h10000000",f"address!=32'h{rom_address:08x}")
    s=re.sub(r'\bslot==10\b','slot==2',s)
    s=replace(s,'end else if(slot==2)begin', '''end else if(slot==3)begin
                        if(!bound || !pause || rst || !cheat_loading || address!=32'h50000000 || length!=`CHT_SIZE)$fatal(1,"unsafe cheat initialization");
                        for(i=0;i<length;i=i+1)begin
                            @(negedge clk);cheat_byte=cheat_data[i];cheat_write=1;
                            @(negedge clk);cheat_write=0;repeat(4)@(negedge clk);
                        end
                    end else if(slot==2)begin''')
    s=replace(s,'address[31:28]==5','address[31:28]==8')
    s=replace(s,"address!=32'h50000000+frame_bytes","address!=32'h80000000+frame_bytes")
    s=replace(s,'    reg [31:0] capacity=32768;', '''    reg [31:0] capacity=32768;
    wire cheat_loading,cheat_armed,cheat_overrun,poke_write;
    reg cheat_write=0,cheat_previous=0;
    reg [7:0] cheat_byte=0;
    reg [7:0] cheat_data[0:`CHT_SIZE-1];
    wire [5:0] genie_total,poke_total;
    wire [12:0] poke_address;
    wire [7:0] poke_value;
    initial $readmemh("cheat.hex",cheat_data);
    always @(posedge clk)cheat_previous<=cheat_loading;
    cheat_loader parser(.clk(clk),.reset(rst || !ready || (cheat_loading && !cheat_previous)),
        .wr(cheat_write),.data(cheat_byte),.eof(cheat_previous && !cheat_loading),
        .genie_count(genie_total),.poke_total(poke_total),.overrun(cheat_overrun),
        .poke_wr(poke_write),.poke_addr(poke_address),.poke_data(poke_value));
    always @(posedge clk)if(poke_write && (poke_address!=13'h123 || poke_value!=8'h7f))$fatal(1,"upstream parser decoded a different code");''')
    s=replace(s,'.SETTLE_CYCLES(20\'d16)',".SETTLE_CYCLES(20'd128)")
    s=replace(s,'begin wait(state==32 && !owned && bound);repeat(4)@(negedge clk);end',
        f'''begin wait(state==32 && !owned && bound);repeat(4)@(negedge clk);
            if({int(case=='matched')} && bindings[{slot}]=="/Assets/{platform}/common/First.{'sg' if platform=='sg1000' else platform}")begin
                if(!cheat_armed || poke_total!=1 || genie_total!=0)$fatal(1,"matched cheat did not arm after parsing");
            end else if(cheat_armed)$fatal(1,"unmatched or failed cheat armed");
        end''')
    s=replace(s,'add_file(`FIRST_SAVE,32768);add_file(`SECOND_SAVE,32768);',
        'add_file(`FIRST_SAVE,32768);add_file(`SECOND_SAVE,32768);\n        if(`AUTOCHEATS)add_file(`FIRST_CHEAT,`CHT_SIZE);')
    s=s.replace('three seeded 256K ordinary saves','three seeded 32K ordinary saves')
    s=s.replace('PASS: F2 bounded atlas/text transfer,','PASS: Native Sega matched/empty cheat gating and real parser, F2 bounded atlas/text transfer,')
    if case=='invalid':
        a=s.index('    initial begin\n        add_file(');b=s.index('    initial begin #10000000',a)
        extension='sg' if platform=='sg1000' else platform
        s=s[:a]+f'''    initial begin
        add_file("/Assets/{namespace}/common/menu.bin",0);add_file(`GAMES_PATH,0);
        add_file("/Assets/{platform}/common/First.{extension}",32768);
        add_file(`FIRST_SAVE,32768);add_file(`FIRST_CHEAT,`CHT_SIZE);
        #100;ready=1;menu(0);press(4);menu(0);press(4);wait(fault);
        if(code!=8'h83 || cheat_armed || !bound || !pause || rst)$fatal(1,"failed cheat discarded game ownership or armed codes");
        press(5);running;
        if(cheat_armed)$fatal(1,"failed payload active after resume");
        $display("PASS: real parser rejects empty/invalid payload; game held paused, B resumes with cheats unarmed");$finish;
    end
'''+s[b:]
    return s


def fixtures(out,platform,case):
    namespace,_,_,_=PROFILES[platform];extension='sg' if platform=='sg1000' else platform
    home='/Assets/'+namespace+'/common/menu.bin';child='/Assets/'+namespace+'/common/libs/test.bin'
    payload=b'cheats = 1\ncheat0_desc = "Test"\ncheat0_code = "00C1-237F"\ncheat0_enable = true\n'
    if case=='invalid':payload=payload.replace(b'00C1-237F',b'00C123-7F') # Mixed-width form is rejected by the actual parser.
    payload+=b'\n'*((-len(payload))%4)
    (out/'cheat.hex').write_text(''.join(f'{v:02x}\n' for v in payload))
    def row(folder,rom,tag='0',cheats=0):
        result=bytearray(1024);struct.pack_into('<4s7I',result,0,b'ENT1',int(folder),0 if folder else 32768,32768,cheats,0,32,80)
        values=[rom,'/Saves/'+namespace+'/common/'+tag*20+'.sav','/Assets/'+namespace+'/cheat/'+tag*20+'.cht']
        for offset,value in zip([32,288,544],values):result[offset:offset+256]=value.encode().ljust(256,b'\0')
        return bytes(result)
    for name,rows in [('root',[row(True,child),row(True,home)]),('games',[
        row(False,'/Assets/'+platform+'/common/First.'+extension,'1',len(payload) if case!='none' else 0),
        row(False,'/Assets/'+platform+'/common/Second.'+extension,'2'),row(True,home)])]:
        count=len(rows);base=64+count*1024;pause=base+count*65536
        raw=struct.pack('<4s5I',b'GBAF',2,count,base,pause,65536).ljust(64,b'\0')+b''.join(rows)
        (out/(name+'.hex')).write_text(''.join(f'{v:02x}\n' for v in raw))
    (out/'paths.vh').write_text('`define GAMES_PATH "'+child+'"\n'+
        '`define FIRST_SAVE "/Saves/'+namespace+'/common/'+('1'*20)+'.sav"\n'+
        '`define SECOND_SAVE "/Saves/'+namespace+'/common/'+('2'*20)+'.sav"\n'+
        '`define FIRST_CHEAT "/Assets/'+namespace+'/cheat/'+('1'*20)+'.cht"\n'+
        '`define CHT_SIZE '+str(len(payload))+'\n`define AUTOCHEATS '+str(int(case!='none'))+'\n')


def run(build,out,platform,source):
    build,out,source=map(lambda p:Path(p).resolve(),(build,out,source))
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
    out.mkdir(parents=True);records=[]
    controller_path=build/'target/pocket/sega_menu.sv';parser=source/'rtl/gg/cheat_loader.sv'
    for case in ['none','matched','invalid']:
        directory=out/case;directory.mkdir();fixtures(directory,platform,case)
        tb=directory/'tb_menu.sv';tb.write_text(bench(platform,case),encoding='utf8')
        r=subprocess.run(['iverilog','-g2012','-I',str(directory),'-s','tb_menu','-o',str(directory/'control.sim'),str(controller_path),str(parser),str(tb)],capture_output=True,text=True,timeout=60)
        (directory/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
        r=subprocess.run(['vvp',str(directory/'control.sim')],cwd=directory,capture_output=True,text=True,timeout=60)
        (directory/'simulation.log').write_text(r.stdout+r.stderr);print(case+': '+'\n'.join(r.stdout.splitlines()[-4:]));r.check_returncode()
        if 'PASS:' not in r.stdout:raise ValueError('No control pass marker')
        records.append({'case':case,'result':'passed','bench_sha256':hashlib.sha256(tb.read_bytes()).hexdigest()})
    (out/'receipt.json').write_text(json.dumps({'result':'passed','platform':platform,'scope':'Actual prepared controller and upstream cheat parser, simulated APF/file/video state. No game CPU, physical RAM/card, cheat gameplay or save durability.',
        'cases':records,'controller_sha256':hashlib.sha256(controller_path.read_bytes()).hexdigest(),'parser_sha256':hashlib.sha256(parser.read_bytes()).hexdigest()},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['build','out','source']:p.add_argument('--'+name,required=True)
    p.add_argument('--platform',choices=PROFILES,required=True);a=p.parse_args();run(a.build,a.out,a.platform,a.source)
