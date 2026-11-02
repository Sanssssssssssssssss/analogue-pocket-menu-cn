#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare the real CoverFlow raster through a modeled physical CellRAM bus."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
from prepare_psram import build,ROOT,HERE


def once(s,old,new):
    if s.count(old)!=1:raise ValueError('Raster anchor changed: '+old[:80])
    return s.replace(old,new)


def bench(gba=False):
    s=(HERE/'tb_view.sv').read_text(encoding='utf8')
    s=once(s,'always #1.35 clk=~clk;','always #6.734 clk=~clk;')
    s=once(s,'always #1 sys=~sys;','always #5 sys=~sys;')
    s=once(s,'always #(GAPS ? 12:15) vid=~vid;',
        'always #59.604644775390625 vid=~vid;' if gba else 'always #93.123 vid=~vid;')
    if gba:s=once(s,'parameter GAPS=0;','parameter GAPS=1;')
    s=once(s,'coverflow_view #(.CB(3)) dut','coverflow_psram_view #(.CB(3)) dut')
    s=once(s,'.clk_sys(ASYNC_BRIDGE ? clk:sys)','.clk_sys(clk)')
    if gba:
        s=once(s,'always #5 sys=~sys;','always #4.967053731282552 sys=~sys;')
        s=once(s,'.clk_sys(clk)','.clk_sys(sys)')
        s=once(s,'if(GAPS==0 || SHOWCASE)begin','if(1)begin')
    s=once(s,'reg done=0;','wire done;')
    s=once(s,'reg [31:0] data=0;','wire [31:0] data;')
    a=s.index('    always @(posedge sys)begin\n        done<=0;');b=s.index('    cover_picker #',a)
    s=s[:a]+'''    always @(posedge sys)if(reference.tick)ref_data<=texture(reference.sd_addr-24'h400000);
    always @(posedge clk)if(request)requests<=requests+1;
    reg upload_begin=0,upload_we=0;
    reg [6:0] upload_slot=0;
    reg [27:0] upload_address=0;
    reg [15:0] upload_data=0;
    wire upload_complete,ram_fault,ram_idle;
    wire [21:16] ca;
    wire [15:0] dq;
    wire cclk,adv,cre,ce0,ce1,oe,we,ub,lb;
    integer physical_reads,physical_writes;
    coverflow_psram_cache images(.clk(clk),.enable(1'b1),.invalidate(1'b0),.begin_upload(upload_begin),.upload_slot(upload_slot),
        .write_en(upload_we),.write_addr(upload_address),.write_data(upload_data),.upload_ready(upload_complete),.idle(ram_idle),
        .request(request),.word_address(address),.done(done),.data(data),.fault(ram_fault),
        .cram_a(ca),.cram_dq(dq),.cram_wait(1'b0),.cram_clk(cclk),.cram_adv_n(adv),.cram_cre(cre),
        .cram_ce0_n(ce0),.cram_ce1_n(ce1),.cram_oe_n(oe),.cram_we_n(we),.cram_ub_n(ub),.cram_lb_n(lb));
    sim_cellram physical_memory(.a(ca),.dq(dq),.clk(cclk),.adv_n(adv),.cre(cre),.ce0_n(ce0),.ce1_n(ce1),
        .oe_n(oe),.we_n(we),.ub_n(ub),.lb_n(lb),.reads(physical_reads),.writes(physical_writes));
    task upload(input integer slot);
        integer n;
        begin
            @(negedge clk);upload_slot=slot;upload_begin=1;
            @(negedge clk);upload_begin=0;
            for(n=0;n<22784;n=n+1)begin
                upload_we=1;upload_address=28'h2000000+(slot<<16)+n*2;
                upload_data=texture((slot<<15)+n);@(negedge clk);upload_we=0;
                repeat(n[0] ? 70:3)@(negedge clk);
                if(ram_fault)$fatal(1,"CellRAM queue/address fault during upload");
            end
            wait(upload_complete);repeat(3)@(negedge clk);
        end
    endtask
'''+s[b:]
    if gba:
        s=once(s,'coverflow_psram_cache images(.clk(clk)', 'coverflow_psram_cache images(.clk(sys)')
        a=s.index('    task upload(input integer slot);');b=s.index('    endtask',a)
        block=s[a:b].replace('@(negedge clk)','@(negedge sys)').replace('70:3','96:3')
        s=s[:a]+block+s[b:]
    s=once(s,'if(fault || underrun)$fatal','if(fault || underrun || ram_fault)$fatal')
    s=once(s,'        repeat(160)@(negedge clk);',
        '        repeat(160)@(negedge clk);\n        for(i=0;i<5;i=i+1)upload(i);')
    a=s.index('        if(SHOWCASE)begin\n            selected=4;')
    b=s.index('        $display("PASS: %0d full raster',a)
    s=s[:a]+'''        fork
            begin wait(checking);upload(127);end
            begin
                one_frame(0);
                animated=1;direction=0;pose=0;one_frame(1);
                direction=1;pose=3;one_frame(2);
                pose=7;one_frame(3);
            end
        join
'''+s[b:]
    s=once(s,'#160000000;','#1000000000;')
    return s


def run(out,source,gba=False):
    out=build(out,source,fast_response=gba,clock_speed=100.663296 if gba else 74.25)
    for name in ['font5x7.hex','font_cn_width.hex','font5x7_width.hex']:
        shutil.copy2(ROOT/'core/src'/name,out/name)
    reference=out/'coverflow_reference.sv';raw=(ROOT/'core/src/core/cover_picker.sv').read_text(encoding='utf8')
    reference.write_text(once(raw,'facc  <= (xs - fx[fk]) * step_lut[S];',
        "facc  <= ($signed(xs) - $signed(fx[fk])) * $signed({1'b0, step_lut[S]});"),encoding='utf8')
    tb=out/'tb_view.sv';tb.write_text(bench(gba),encoding='utf8')
    inputs=[reference,out/'coverflow_geometry.sv',out/'coverflow_psram_view.sv',out/'coverflow_line_fetch16.sv',
        out/'coverflow_psram_cache.sv',out/'coverflow_psram.sv',HERE/'sim_ram.sv',HERE/'sim_cellram.sv',tb]
    obj=out/'obj';exe=obj/'psram_raster'
    r=subprocess.run(['verilator','--binary','--timing','--top-module','tb_view','--build-jobs','4','-Wno-fatal',
        '--Mdir',str(obj),'-o','psram_raster',*map(str,inputs)],capture_output=True,text=True,timeout=180)
    (out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run([str(exe)],cwd=out,capture_output=True,text=True,timeout=240)
    (out/'simulation.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
    if 'PASS:' not in r.stdout:raise ValueError('No physical-model raster pass marker')
    clock='8.388608 MHz with 4/5 pixel enable' if gba else '5.369 MHz'
    (out/'receipt.json').write_text(json.dumps({'result':'passed','scope':f'Four complete raster frames at actual 74.25 MHz bridge / {clock} pixel clock ratios, pin-level synthetic CellRAM model, full atlas uploaded concurrently with raster work',
        'memory_clock_MHz':100.663296 if gba else 74.25,
        'reference_exception':'Test-only signed-clipping correction; frozen inputs unchanged',
        'physical_acceptance':'pending; behavioral peripheral model does not establish board timing',
        'inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--gba-source',required=True)
    p.add_argument('--gba',action='store_true',help='Use the native GBA video clock and 4/5 menu pixel enable')
    a=p.parse_args();run(a.out,a.gba_source,a.gba)
