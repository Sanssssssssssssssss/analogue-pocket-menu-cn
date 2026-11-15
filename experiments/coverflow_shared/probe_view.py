#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Render synthetic textures through the real GB/GBC and extracted compositor."""
import argparse,hashlib,json,shutil,struct,subprocess,sys
from pathlib import Path
from prepare_view import prepare,ROOT,HERE

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',required=True);p.add_argument('--intel-model',required=True)
p.add_argument('--simulator',choices=('verilator','iverilog'),default='verilator')
p.add_argument('--showcase',action='store_true',help='Render all eight real animation poses with original icons and a Chinese test title')
p.add_argument('--compact',action='store_true')
p.add_argument('--async-bridge',action='store_true')
a=p.parse_args();out=prepare(a.out,a.compact)
for name in ['font5x7.hex','font_cn_width.hex','font5x7_width.hex']:
    shutil.copy2(ROOT/'core/src'/name,out/name)
original=ROOT/'core/src/core/cover_picker.sv'
reference=out/'coverflow_reference.sv'
raw=original.read_text(encoding='utf8')
before='facc  <= (xs - fx[fk]) * step_lut[S];'
after="facc  <= ($signed(xs) - $signed(fx[fk])) * $signed({1'b0, step_lut[S]});"
if raw.count(before)!=1:raise ValueError('Clipped-coordinate reference anchor changed')
reference.write_text(raw.replace(before,after),encoding='utf8')
reference_note={'original_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'reference_patch':'Explicit signed multiplication for the original clipped-left-coordinate bug only; frozen repository source unchanged',
    'original_expression':before,'replacement_expression':after,'witness':'tb_reference_fetch.sv with actual frozen source and Intel models confirms the legacy unsigned-wrap samples'}
(out/'reference-scope.json').write_text(json.dumps(reference_note,indent=2)+'\n')
inputs=[reference,out/'coverflow_geometry.sv',out/'coverflow_view.sv',out/'coverflow_line_fetch.sv',
        HERE/'sim_ram.sv',HERE/'memory_bridge.sv',HERE/'tb_view.sv']
vendor_inputs=[HERE/'tb_ram.sv',HERE/'sim_ram.sv',out/'coverflow_dpram_ce.v',out/'picker_dpram.v',Path(a.intel_model).resolve()]
r=subprocess.run(['iverilog','-g2012','-DCF_RAM_VALIDATE','-s','tb_ram','-o',str(out/'ram-validation.sim'),*map(str,vendor_inputs)],capture_output=True,text=True,timeout=60)
(out/'ram-build.log').write_text(r.stdout+r.stderr);r.check_returncode()
r=subprocess.run(['vvp',str(out/'ram-validation.sim')],capture_output=True,text=True,timeout=60)
(out/'ram-validation.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr,flush=True);r.check_returncode()
if 'PASS:' not in r.stdout:raise ValueError('RAM backend not validated')
if a.showcase:
    sys.path.insert(0,str(ROOT/'tools'))
    import build_library as gb
    from menu_icons import cover_bytes
    from PIL import Image
    blobs=[cover_bytes(k).ljust(65536,b'\0') for k in ('zelda','pokemon','rpg','fighting','puzzle')]
    (out/'showcase-art.hex').write_text(''.join(f'{v[0]:04x}\n' for v in struct.iter_unpack('<H',b''.join(blobs))))
    width,columns,_,missing=gb.columns('星际旅程',gb.font())
    if width!=64 or missing:raise ValueError('Unexpected showcase font')
    (out/'showcase-text.hex').write_text(''.join(f'{v[0]:04x}\n' for v in struct.iter_unpack('<H',columns+bytes(1024))))
results=[]
for gaps in ((1,) if a.showcase or a.async_bridge else (0,1)):
    sim=out/f'view-{gaps}.sim'
    if a.simulator=='verilator':
        obj=out/f'obj-{gaps}';sim=obj/'view_probe'
        command=['verilator','--binary','--timing','--top-module','tb_view','--build-jobs','4','-Wno-fatal',f'-GGAPS={gaps}',f'-GSHOWCASE={int(a.showcase)}',f'-GASYNC_BRIDGE={int(a.async_bridge)}',
                 '--Mdir',str(obj),'-o','view_probe',*map(str,inputs)]
    else:
        command=['iverilog','-g2012','-s','tb_view',f'-Ptb_view.GAPS={gaps}',f'-Ptb_view.SHOWCASE={int(a.showcase)}',f'-Ptb_view.ASYNC_BRIDGE={int(a.async_bridge)}','-o',str(sim),*map(str,inputs)]
    r=subprocess.run(command,capture_output=True,text=True,timeout=180)
    (out/f'build-{gaps}.log').write_text(r.stdout+r.stderr);r.check_returncode()
    with (out/f'simulation-{gaps}.log').open('w') as log:
        command=[str(sim)] if a.simulator=='verilator' else ['vvp','-v',str(sim)]
        process=subprocess.Popen(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,text=True)
        try:code=process.wait(timeout=600)
        except BaseException:
            process.terminate();process.wait(timeout=10);raise
    output=(out/f'simulation-{gaps}.log').read_text()
    print(output,flush=True)
    if code:raise subprocess.CalledProcessError(code,process.args)
    if 'PASS:' not in output:raise ValueError('No raster pass marker')
    results.append({'pixel_enable':'4/5' if gaps else '1','result':'passed','log':f'simulation-{gaps}.log'})
(out/'receipt.json').write_text(json.dumps({'result':'passed','scope':'GB/GBC compositor with one documented signed-clipping correction in a test-only reference copy vs extracted renderer; synthetic art/title columns, no game CPU/card/hardware',
    'reference':reference_note,
    'simulator':a.simulator,'ram_backend':'portable registered-address RAM; crosschecked in Icarus against Intel model before raster test',
    'ram_validation_inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in vendor_inputs},
    'showcase':a.showcase,'compact':a.compact,'async_bridge':a.async_bridge,'cases':results,'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}},indent=2)+'\n')
if a.showcase:
    frames=[Image.open(out/f'pose-{i}.ppm').convert('RGB') for i in range(10)]
    frames[-1].save(out/'preview.png')
    frames[0].save(out/'preview.gif',save_all=True,append_images=frames[1:],duration=[600]+[20]*8+[600],loop=0,disposal=2)
