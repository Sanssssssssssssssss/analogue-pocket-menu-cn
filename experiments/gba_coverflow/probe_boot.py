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


def run(build,out,intel,full_animation=False):
    build,out,intel=Path(build).resolve(),Path(out).resolve(),Path(intel).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
    out.mkdir(parents=True)
    f1=fixtures(out/'f1');f2=out/'f2';atlas.upgrade(f1/'library',f2)
    raw=(f2/'Assets/gbalab/common/menu.bin').read_bytes()
    if int.from_bytes(raw[8:12],'little')!=2:raise ValueError('Expected two synthetic root covers')
    (out/'page.hex').write_text(''.join(f'{v:02x}\n' for v in raw))
    core=build/'src/fpga/core'
    top=(core/'core_top.sv').read_text(encoding='utf8')
    start=top.index('// Reuse the working GG cover cache')
    end=top.index('assign ui_prepare_ready=',start)
    bench=(HERE/'tb_boot.sv').read_text(encoding='utf8')
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
    names=['gba_menu.sv','coverflow_geometry.sv','coverflow_psram_view.sv','coverflow_line_fetch16.sv',
        'coverflow_psram.sv','coverflow_psram_cache.sv','coverflow_dpram_ce.v','picker_dpram.v']
    inputs=[core/name for name in names]+[build/'src/fpga/pocket/data_loader.sv',build/'src/fpga/apf/common.v',
        out/'commands.v',out/'table.sv',ROOT/'experiments/coverflow_shared/sim_cellram.sv',tb,intel]
    r=subprocess.run(['iverilog','-g2012','-s','tb_coverflow_boot','-o',str(out/'boot.sim'),*map(str,inputs)],
        capture_output=True,text=True,timeout=60)
    (out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
    with (out/'simulation.log').open('w') as log:
        command=['vvp',str(out/'boot.sim')]+(['+full_animation'] if full_animation else [])
        process=subprocess.Popen(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,text=True)
        try:code=process.wait(timeout=2400 if full_animation else 900)
        except BaseException:
            process.terminate();process.wait(timeout=10);raise
    output=(out/'simulation.log').read_text();print(output,flush=True)
    if code:raise subprocess.CalledProcessError(code,process.args)
    if 'PASS:' not in output:raise ValueError('No complete boot/animation pass marker')
    (out/'receipt.json').write_text(json.dumps({'result':'passed',
        'scope':'Generated production UI wiring, actual APF engine, Intel FIFO/RAM and CellRAM pin model; game held/reset with VS=0. Real GBA pixel clock, complete uploads without redundant reads and key-triggered animation.',
        'animation_scope':'Eight sequential key-driven poses completed' if full_animation else 'Key starts the actual animation; full compositor and all geometry poses are checked by the separate raster/geometry probes',
        'modeled':'Synthetic host/file bytes, native ready/idle inputs and external CellRAM; no game CPU, card, firmware or save durability.',
        'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs+[core/'core_top.sv',HERE/'tb_boot.sv',Path(__file__)]}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('build','out','intel-model'):p.add_argument('--'+name,required=True)
    p.add_argument('--full-animation',action='store_true',help='Also run eight complete native-rate frames in the slower Intel model')
    a=p.parse_args();run(a.build,a.out,a.intel_model,a.full_animation)
