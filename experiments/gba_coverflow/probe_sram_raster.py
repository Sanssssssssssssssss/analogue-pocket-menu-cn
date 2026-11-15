#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare the five-slot GBA SRAM renderer to the accepted GB/GBC compositor."""
import argparse,hashlib,json,shutil,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SHARED=ROOT/'experiments/coverflow_shared'
sys.path.insert(0,str(ROOT/'tools'))
import build_library as gb
from menu_icons import cover_bytes
from PIL import Image


def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Raster anchor changed: '+old[:80])
    return text.replace(old,new)


def bench():
    s=(SHARED/'tb_view.sv').read_text(encoding='utf8')
    s=replace(s,'parameter GAPS=0;','parameter GAPS=1;')
    s=replace(s,'parameter SHOWCASE=0;','parameter SHOWCASE=1;')
    s=replace(s,'selected=0,total=5;','selected=1,total=5;')
    s=replace(s,'always #1.35 clk=~clk;','always #6.734 clk=~clk;')
    s=replace(s,'always #1 sys=~sys;','always #4.965 sys=~sys;')
    s=replace(s,'always #(GAPS ? 12:15) vid=~vid;','always #59.604644775390625 vid=~vid;')
    s=replace(s,'coverflow_view #(.CB(3)) dut','coverflow_assoc_view #(.CB(3)) dut')
    s=replace(s,'.cache_game(cache_game),','.cache_game(cache_game),.cache_slot(cache_game[2:0]),')
    s=replace(s,'reg done=0;','wire done;')
    s=replace(s,'reg [31:0] data=0;','wire [31:0] data;')
    a=s.index('    always @(posedge sys)begin\n        done<=0;')
    b=s.index('    cover_picker #',a)
    s=s[:a]+'''    always @(posedge sys)if(reference.tick)ref_data<=texture(reference.sd_addr-24'h400000);
    always @(posedge sys)if(request)requests<=requests+1;
    reg upload_begin=0,upload_we=0;
    reg [2:0] upload_slot=0;
    reg [27:0] upload_address=0;
    reg [15:0] upload_data=0;
    wire upload_complete,ram_fault,ram_idle;
    wire [16:0] sa;
    wire [15:0] dq;
    wire oe,we,ub,lb;
    integer physical_reads,physical_writes;
    coverflow_sram_cache images(.clk(sys),.enable(1'b1),.invalidate(1'b0),.begin_upload(upload_begin),.upload_slot(upload_slot),
        .write_en(upload_we),.write_addr(upload_address),.write_data(upload_data),.upload_ready(upload_complete),.idle(ram_idle),
        .request(request),.word_address(address),.done(done),.data(data),.fault(ram_fault),
        .sram_a(sa),.sram_dq(dq),.sram_oe_n(oe),.sram_we_n(we),.sram_ub_n(ub),.sram_lb_n(lb));
    sim_coverflow_sram physical_memory(.clock(sys),.a(sa),.dq(dq),.oe_n(oe),.we_n(we),.ub_n(ub),.lb_n(lb),
        .reads(physical_reads),.writes(physical_writes));
    task upload(input integer slot);
        integer n;
        begin
            @(negedge sys);upload_slot=slot;upload_begin=1;
            @(negedge sys);upload_begin=0;
            for(n=0;n<22784;n=n+1)begin
                upload_we=1;upload_address=28'h2000000+(slot<<16)+n*2;
                upload_data=texture((slot<<15)+n);@(negedge sys);upload_we=0;
                repeat(n[0] ? 96:3)@(negedge sys);
                if(ram_fault)$fatal(1,"SRAM queue/address fault during raster upload");
            end
            wait(upload_complete);repeat(3)@(negedge sys);
        end
    endtask
'''+s[b:]
    s=replace(s,'if(fault || underrun)$fatal','if(fault || underrun || ram_fault)$fatal')
    s=replace(s,'        repeat(160)@(negedge clk);',
        '        repeat(160)@(negedge clk);\n        for(i=0;i<4;i=i+1)upload(i);')
    s=replace(s,'for(i=0;i<5;i=i+1)begin','for(i=0;i<4;i=i+1)begin')
    a=s.index('        if(SHOWCASE)begin\n            selected=4;')
    b=s.index('        $display("PASS: %0d full raster',a)
    s=s[:a]+'''        selected=1;
        fork
            begin
                wait(checking);upload(4);
                @(negedge clk);cache_game=4;cache_commit=1;
                force reference.tag_wa=3'd4;force reference.tag_wd=12'h804;force reference.tag_we=1;
                @(negedge clk);cache_commit=0;force reference.tag_we=0;
            end
            one_frame(0);
        join
        animated=1;direction=0;selected=2;
        for(i=0;i<8;i=i+1)begin pose=i;one_frame(i+1);end
        direction=1;selected=1;
        for(i=0;i<8;i=i+1)begin pose=i;one_frame(i+9);end
        animated=0;one_frame(17);
        if(physical_writes!=113920)$fatal(1,"five physical cover uploads incomplete");
'''+s[b:]
    return replace(s,'#160000000;','#2000000000;')


def run(build,out,intel):
    build,out,intel=map(lambda p:Path(p).resolve(),(build,out,intel))
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh local output required')
    out.mkdir(parents=True)
    core=build/'src/fpga/core'
    for name in ('font5x7.hex','font_cn_width.hex','font5x7_width.hex'):
        shutil.copy2(ROOT/'core/src'/name,out/name)
    shutil.copy2(build/'src/fpga/build/font_cn.hex',out/'font_cn.hex')
    ram_inputs=[SHARED/'tb_ram.sv',SHARED/'sim_ram.sv',core/'coverflow_dpram_ce.v',core/'picker_dpram.v',intel]
    r=subprocess.run(['iverilog','-g2012','-DCF_RAM_VALIDATE','-s','tb_ram','-o',str(out/'ram.sim'),*map(str,ram_inputs)],capture_output=True,text=True,timeout=60)
    (out/'ram-build.log').write_text(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run(['vvp',str(out/'ram.sim')],cwd=out,capture_output=True,text=True,timeout=60)
    (out/'ram-validation.log').write_text(r.stdout+r.stderr);r.check_returncode()
    if 'PASS:' not in r.stdout:raise ValueError('RAM calibration failed')
    icons=[cover_bytes(k).ljust(65536,b'\0') for k in ('zelda','pokemon','rpg','fighting','puzzle')]
    (out/'showcase-art.hex').write_text(''.join(f'{p[0]:04x}\n' for p in struct.iter_unpack('<H',b''.join(icons))))
    width,columns,_,missing=gb.columns('星际旅程',gb.font())
    if width!=64 or missing:raise ValueError('Synthetic Chinese title failed')
    (out/'showcase-text.hex').write_text(''.join(f'{p[0]:04x}\n' for p in struct.iter_unpack('<H',columns+bytes(1024))))
    raw=(ROOT/'core/src/core/cover_picker.sv').read_text(encoding='utf8')
    raw=replace(raw,'facc  <= (xs - fx[fk]) * step_lut[S];',
        "facc  <= ($signed(xs) - $signed(fx[fk])) * $signed({1'b0, step_lut[S]});")
    reference=out/'coverflow_reference.sv';reference.write_text(raw,encoding='utf8')
    tb=out/'tb_view.sv';tb.write_text(bench(),encoding='utf8')
    inputs=[reference,*[core/n for n in ('coverflow_geometry.sv','coverflow_assoc_view.sv','coverflow_assoc_cache.sv','coverflow_line_fetch.sv','coverflow_sram_cache.sv')],SHARED/'sim_ram.sv',HERE/'sim_sram.sv',tb]
    exe=out/'obj/sram_raster'
    r=subprocess.run(['verilator','--binary','--timing','--top-module','tb_view','--build-jobs','4','-Wno-fatal','--Mdir',str(exe.parent),'-o',exe.name,*map(str,inputs)],capture_output=True,text=True,timeout=240)
    (out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
    with (out/'simulation.log').open('w') as stream:
        r=subprocess.run([str(exe)],cwd=out,stdout=stream,stderr=subprocess.STDOUT,text=True,timeout=900)
    output=(out/'simulation.log').read_text();print(output,flush=True);r.check_returncode()
    if 'PASS: 18 full raster frames' not in output:raise ValueError('Full bidirectional comparison missing')
    frames=[Image.open(out/f'pose-{i}.ppm').convert('RGB') for i in range(18)]
    frames[0].save(out/'preview.png')
    frames[0].save(out/'preview.gif',save_all=True,append_images=frames[1:],duration=[500]+[100]*16+[500],loop=0,disposal=2)
    proof={'result':'passed','scope':'18 full GBA-clock frames / 2,019,600 golden comparisons, five physical SRAM atlases, concurrent upload, all eight poses both directions, synthetic Chinese text and original placeholder art',
        'reference_exception':'Documented signed-clipping correction in a test-only copy; frozen GB/GBC source unchanged',
        'RAM_backend':'Portable registered-address RAM, crosschecked against the actual Intel model before this run',
        'external_memory_model':'Datasheet AS6C2016-55 plus 4.25ns launch/return budgets, 9.930ns SRAM clock; not a vendor model or hardware acceptance',
        'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs+ram_inputs}}
    (out/'receipt.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('build','out','intel-model'):p.add_argument('--'+name,required=True)
    a=p.parse_args();run(a.build,a.out,a.intel_model)
