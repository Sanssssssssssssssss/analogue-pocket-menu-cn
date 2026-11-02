#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare the five-slot cache and actual packed NES art RAM with GB/GBC RTL."""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SHARED=ROOT/'experiments/coverflow_shared'
sys.path.insert(0,str(SHARED))
from prepare_assoc import build


def once(s,old,new):
    if s.count(old)!=1:raise ValueError('Bench anchor changed: '+old[:80])
    return s.replace(old,new)


def bench():
    s=(SHARED/'tb_view.sv').read_text(encoding='utf8')
    s=once(s,'coverflow_view #(.CB(3)) dut','coverflow_assoc_view #(.CB(3)) dut')
    s=once(s,'.cache_game(cache_game),','.cache_game(cache_game),.cache_slot(3\'(4-cache_game)),')
    s=once(s,'.clk_sys(ASYNC_BRIDGE ? clk:sys)','.clk_sys(clk)')
    s=once(s,'reg done=0;','wire done;')
    s=once(s,'reg [31:0] data=0;','wire [31:0] data;')
    a=s.index('    always @(posedge sys)begin\n        done<=0;')
    b=s.index('    cover_picker #',a)
    s=s[:a]+'''    always @(posedge sys)if(reference.tick)ref_data<=texture(reference.sd_addr-24'h400000);
    always @(posedge clk)if(request)requests<=requests+1;
    reg upload_begin=0,upload_we=0;
    reg [2:0] upload_slot=0;
    reg [27:0] upload_address=0;
    reg [15:0] upload_data=0;
    wire upload_complete,ram_fault;
    nes_coverflow_art_ram images(.clk(clk),.enable(1'b1),.invalidate(1'b0),.begin_upload(upload_begin),.upload_slot(upload_slot),
        .write_en(upload_we),.write_addr(upload_address),.write_data(upload_data),.upload_ready(upload_complete),
        .request(request),.word_address(address),.done(done),.data(data),.fault(ram_fault));
'''+s[b:]
    s=once(s,'integer comparisons=0,pixels=0,frames=0,fd=0,i;',
        'integer comparisons=0,pixels=0,frames=0,fd=0,i,word_index;')
    s=once(s,'{dut.vx[slot],dut.vs_[slot],dut.vb[slot],dut.vg[slot],dut.vv[slot],dut.vl[slot]}',
        '{dut.vx[slot],dut.vs_[slot],dut.vb[slot],3\'(4-dut.vg[slot]),dut.vv[slot],dut.vl[slot]}')
    s=once(s,'if(fault || underrun)$fatal', 'if(fault || underrun || ram_fault)$fatal')
    s=once(s,'        repeat(160)@(negedge clk);', '''        // Upload the real packed 128/80 textures with a deliberately reversed
        // physical mapping. Address truncation/modulo bugs cannot pass this.
        for(i=0;i<5;i=i+1)begin
            @(negedge clk);upload_slot=4-i;upload_begin=1;
            @(negedge clk);upload_begin=0;
            for(word_index=0;word_index<22784;word_index=word_index+1)begin
                upload_we=1;upload_address=28'h2000000+((4-i)<<16)+word_index*2;
                upload_data=texture((i<<15)+word_index);@(negedge clk);
            end
            upload_we=0;#0.1;if(!upload_complete || ram_fault)$fatal(1,"atlas upload fence");
        end
        repeat(160)@(negedge clk);''')
    return s


def run(out):
    out=build(out)
    for name in ['font5x7.hex','font_cn_width.hex','font5x7_width.hex']:
        shutil.copy2(ROOT/'core/src'/name,out/name)
    reference=out/'coverflow_reference.sv'
    raw=(ROOT/'core/src/core/cover_picker.sv').read_text(encoding='utf8')
    reference.write_text(once(raw,'facc  <= (xs - fx[fk]) * step_lut[S];',
        "facc  <= ($signed(xs) - $signed(fx[fk])) * $signed({1'b0, step_lut[S]});"),encoding='utf8')
    tb=out/'tb_view.sv';tb.write_text(bench(),encoding='utf8')
    inputs=[reference,out/'coverflow_geometry.sv',out/'coverflow_assoc_view.sv',out/'coverflow_assoc_cache.sv',
        out/'coverflow_line_fetch.sv',SHARED/'sim_ram.sv',HERE/'art_ram.sv',tb]
    obj=out/'obj';exe=obj/'assoc_raster'
    command=['verilator','--binary','--timing','--top-module','tb_view','--build-jobs','4','-Wno-fatal',
        '--Mdir',str(obj),'-o','assoc_raster',*map(str,inputs)]
    r=subprocess.run(command,capture_output=True,text=True,timeout=180)
    (out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run([str(exe)],cwd=out,capture_output=True,text=True,timeout=240)
    (out/'simulation.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
    if 'PASS:' not in r.stdout:raise ValueError('No raster pass marker')
    (out/'receipt.json').write_text(json.dumps({'result':'passed','scope':'Four full raster frames with synthetic textures and Unicode text; actual five-slot associative cache and packed NES art RAM; static and both movement directions',
        'reference_exception':'Test reference only corrects the documented original signed-clipping bug; frozen inputs unchanged',
        'ram_backend':'Packed art RAM RTL plus portable line/text RAM previously crosschecked against Intel model',
        'physical_slot_order':'4 minus logical game ID, verifies every visible slot translation',
        'hardware_playtest':'pending','inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);a=p.parse_args();run(a.out)
