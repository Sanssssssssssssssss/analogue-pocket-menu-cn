#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run generated GBA menu wiring with actual APF/FIFO/RAM and modeled CellRAM."""
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'experiments/gba_menu'))
from prepare_test import prepare as fixtures
spec=importlib.util.spec_from_file_location('boot_atlas',HERE/'library.py')
atlas=importlib.util.module_from_spec(spec);spec.loader.exec_module(atlas)


def run(build,out,intel,full_animation=False,hierarchy=False,simulator='iverilog'):
    build,out,intel=Path(build).resolve(),Path(out).resolve(),Path(intel).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
    out.mkdir(parents=True)
    f1=fixtures(out/'f1');source=f1/'library';f2=out/'f2'
    if hierarchy:
        # Match the reported 2 -> 12 entry transition without personal files.
        card=out/'hierarchy-card'
        synthetic=(f1/'synthetic-card/Assets/gba/common/First.gba').read_bytes()
        for index in range(11):
            rom=card/f'Assets/gba/common/Group{index:02d}/Synthetic.gba'
            rom.parent.mkdir(parents=True,exist_ok=True)
            rom.write_bytes(synthetic+bytes([index])*4)
        source=out/'hierarchy-f1';atlas.old.build(card,source)
    atlas.upgrade(source,f2)
    raw=(f2/'Assets/gbalab/common/menu.bin').read_bytes()
    if int.from_bytes(raw[8:12],'little')!=2:raise ValueError('Expected two synthetic root covers')
    (out/'page.hex').write_text(''.join(f'{v:02x}\n' for v in raw))
    # Follow the first root record rather than filesystem enumeration order.
    child=f2/raw[96:352].split(b'\0',1)[0].decode().lstrip('/')
    child_raw=child.read_bytes()
    child_count=int.from_bytes(child_raw[8:12],'little')
    if child_count!=(12 if hierarchy else 3):raise ValueError('Unexpected synthetic child count')
    (out/'child.hex').write_text(''.join(f'{v:02x}\n' for v in child_raw))
    core=build/'src/fpga/core'
    top=(core/'core_top.sv').read_text(encoding='utf8')
    sram='coverflow_sram_cache cf_images' in top
    start=top.index('// Pocket Lab five-slot CoverFlow cache' if sram else '// Reuse the working GG cover cache')
    end=top.index('assign ui_prepare_ready=',start)
    bench=(HERE/'tb_boot.sv').read_text(encoding='utf8')
    if bench.count('CHILD_MENU_PATH')!=1:raise ValueError('Child path anchor changed')
    bench=bench.replace('CHILD_MENU_PATH','/'+child.relative_to(f2).as_posix())
    bench=bench.replace('CHILD_MENU_COUNT',str(child_count)).replace('CHILD_PREFETCH_COVERS',str(min(child_count,5 if sram else 11)))
    if sram:
        a=bench.index('    integer physical_reads,physical_writes;')
        b=bench.index('    reg [7:0] page',a)
        bench=bench[:a]+'''    wire [16:0] sram_a;
    wire [15:0] sram_dq;
    wire sram_oe_n,sram_we_n,sram_ub_n,sram_lb_n;
    integer physical_reads,physical_writes;
    sim_coverflow_sram physical_memory(.clock(clk_sys),.a(sram_a),.dq(sram_dq),.oe_n(sram_oe_n),.we_n(sram_we_n),
        .ub_n(sram_ub_n),.lb_n(sram_lb_n),.reads(physical_reads),.writes(physical_writes));
'''+bench[b:]
        bench=bench.replace('cf_images.uploading','cf_images.receiving')
        bench=bench.replace('NAV_STEPS=0','NAV_STEPS=16' if hierarchy else 'NAV_STEPS=0')
        bench=bench.replace('#600000000;','#(64\'d10000000000);')
        bench=bench.replace('CellRAM','SRAM')
    if simulator=='verilator':bench=bench.replace('Intel FIFO/RAM','vendor FIFO and calibrated RAM')
    if bench.count('/* GENERATED_UI_WIRING */')!=1:raise ValueError('Boot bench anchor changed')
    tb=out/'tb_boot.sv';tb.write_text(bench.replace('/* GENERATED_UI_WIRING */',top[start:end]),encoding='utf8')
    # Named ports are equivalent; Icarus rejects the upstream's omitted outputs.
    command=core/'core_bridge_cmd.v'
    text=command.read_text(encoding='utf8').replace('synch_3 s01(bridge_endian_little, endian_little_s, clk);',
        'synch_3 s01(.i(bridge_endian_little),.o(endian_little_s),.clk(clk),.rise(),.fall());')
    (out/'commands.v').write_text(text,encoding='utf8')
    text=(ROOT/'experiments/gba_menu/tb_commands.sv').read_text()
    start=text.index('module mf_datatable');end=text.index('endmodule',start)+len('endmodule')
    (out/'table.sv').write_text(text[start:end])
    shutil.copy2(build/'src/fpga/build/font_cn.hex',out/'font_cn.hex')
    names=['gba_menu.sv','coverflow_geometry.sv']+(['coverflow_assoc_view.sv','coverflow_assoc_cache.sv','coverflow_line_fetch.sv','coverflow_sram_cache.sv'] if sram else
        ['coverflow_psram_view.sv','coverflow_line_fetch16.sv','coverflow_psram.sv','coverflow_psram_cache.sv'])
    names+=['coverflow_dpram_ce.v','picker_dpram.v']
    if (core/'coverflow_data_loader.sv').is_file():names.append('coverflow_data_loader.sv')
    memory_model=HERE/'sim_sram.sv' if sram else ROOT/'experiments/coverflow_shared/sim_cellram.sv'
    inputs=[core/name for name in names]+[build/'src/fpga/pocket/data_loader.sv',build/'src/fpga/apf/common.v',
        out/'commands.v',out/'table.sv',memory_model,tb,intel]
    if simulator=='verilator':
        shared=ROOT/'experiments/coverflow_shared'
        ram_inputs=[shared/'tb_ram.sv',shared/'sim_ram.sv',core/'coverflow_dpram_ce.v',core/'picker_dpram.v',intel]
        r=subprocess.run(['iverilog','-g2012','-DCF_RAM_VALIDATE','-s','tb_ram','-o',str(out/'ram.sim'),*map(str,ram_inputs)],capture_output=True,text=True,timeout=60)
        (out/'ram-build.log').write_text(r.stdout+r.stderr);r.check_returncode()
        r=subprocess.run(['vvp',str(out/'ram.sim')],cwd=out,capture_output=True,text=True,timeout=60)
        (out/'ram-validation.log').write_text(r.stdout+r.stderr);r.check_returncode()
        if 'PASS:' not in r.stdout:raise ValueError('Portable RAM calibration failed')
        inputs=[p for p in inputs if p.name not in ('coverflow_dpram_ce.v','picker_dpram.v')]+[shared/'sim_ram.sv']
        executable=out/'obj/boot_probe'
        command=['verilator','--binary','--timing','--top-module','tb_coverflow_boot','--build-jobs','4','-Wno-fatal',
            '--Mdir',str(executable.parent),'-o',executable.name,*map(str,inputs)]
    else:
        executable=out/'boot.sim'
        command=['iverilog','-g2012','-s','tb_coverflow_boot','-o',str(executable),*map(str,inputs)]
    r=subprocess.run(command,capture_output=True,text=True,timeout=240)
    (out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
    with (out/'simulation.log').open('w') as log:
        command=([str(executable)] if simulator=='verilator' else ['vvp',str(executable)])+(['+full_animation'] if full_animation else [])+(['+hierarchy'] if hierarchy else [])
        process=subprocess.Popen(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,text=True)
        try:code=process.wait(timeout=2400 if full_animation or hierarchy else 900)
        except BaseException:
            process.terminate();process.wait(timeout=10);raise
    output=(out/'simulation.log').read_text();print(output,flush=True)
    if code:raise subprocess.CalledProcessError(code,process.args)
    if 'PASS:' not in output:raise ValueError('No complete boot/animation pass marker')
    if hierarchy and 'PASS: A opens' not in output:raise ValueError('Hierarchy pass marker missing')
    (out/'receipt.json').write_text(json.dumps({'result':'passed',
        'scope':'Generated production UI wiring, actual APF engine and vendor FIFO, modeled '+('SRAM' if sram else 'CellRAM')+' pins; game held/reset with VS=0. Real GBA pixel clock, complete uploads and key-triggered animation. RAM scope is specified separately.',
        'animation_scope':'Eight sequential key-driven poses completed' if full_animation else 'Key starts the actual animation; full compositor and all geometry poses are checked by the separate raster/geometry probes',
        'hierarchy_scope':'A opens child, its full art/text reload, B returns and root reloads before subsequent input' if hierarchy else 'Not exercised',
        'backend':'Five-slot SRAM' if sram else 'Legacy CellRAM',
        'simulator':simulator,'RAM_scope':'Intel model' if simulator=='iverilog' else 'Portable RAM crosschecked against Intel model before the run; actual vendor FIFO retained',
        'navigation_steps':16 if hierarchy and sram else 0,
        'modeled':'Synthetic host/file bytes, native ready/idle inputs and external memory; no game CPU, card, firmware or save durability.',
        'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs+[core/'core_top.sv',HERE/'tb_boot.sv',Path(__file__)]}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('build','out','intel-model'):p.add_argument('--'+name,required=True)
    p.add_argument('--full-animation',action='store_true',help='Also run eight complete native-rate frames in the slower Intel model')
    p.add_argument('--hierarchy',action='store_true',help='Open a child page and return with actual APF/FIFO/CellRAM wiring')
    p.add_argument('--simulator',choices=('iverilog','verilator'),default='iverilog')
    a=p.parse_args();run(a.build,a.out,a.intel_model,a.full_animation,a.hierarchy,a.simulator)
