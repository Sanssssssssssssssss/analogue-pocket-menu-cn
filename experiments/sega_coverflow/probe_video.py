#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify the Sega pause/error scaler independently of the native game video."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
from controller import ROOT,replace


def run(build,out):
    build,out=Path(build).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
    out.mkdir(parents=True);shutil.copy2(build/'projects/gba_menu_error.hex',out/'gba_menu_error.hex')
    s=(ROOT/'experiments/nes_menu/tb_video.sv').read_text()
    s=replace(s,'always #23 cm=~cm;always #93 cv=~cv;','always #9.312 cm=~cm;always #93.123 cv=~cv;')
    s=replace(s,'reg capture=0;','''reg capture=0,error_capture=0;
    integer scaler_words=0,error_pixels=0;
    always @(negedge cv)if(capture && !de)begin
        if(hs || vs)begin if(rgb!==0)$fatal(1,"scaler bits overlap sync feature field");end
        else if(rgb!==24'h00A000)$fatal(1,"pause/error did not select scaler 5");
        else scaler_words=scaler_words+1;
    end''')
    s=replace(s,'if(rgb!=0)begin','''if(error_capture)begin
            if(rgb!=0 && rgb!==24'he8e6dd)$fatal(1,"unexpected error glyph color");
            if(rgb!=0)error_pixels=error_pixels+1;
        end else if(rgb!=0)begin''')
    s=replace(s,'        owned=0;repeat(341*262*2)', '''        fault=1;wait(visible);repeat(2)@(posedge vs);
        @(negedge cv);error_capture=1;capture=1;@(posedge vs);@(negedge cv);capture=0;
        if(error_pixels==0 || scaler_words<100)$fatal(1,"error glyph or UI scaler path not exercised");
        owned=0;repeat(341*262*2)''')
    s=replace(s,'#180000000;','#500000000;')
    s=replace(s,'PASS: 38400 menu pixels centered in 256x240; RGB332; hide handshake; bit-identical game video/sync bypass',
        'PASS: 38400 centered pause pixels, actual Chinese error glyphs, dedicated scaler 5 with sync isolation, and 256 native video bypass patterns')
    tb=out/'tb_video.sv';tb.write_text(s,encoding='utf8')
    module=build/'target/pocket/menu_video.sv';inputs=[module,tb,out/'gba_menu_error.hex']
    r=subprocess.run(['iverilog','-g2012','-s','tb_video','-o',str(out/'video.sim'),str(module),str(tb)],capture_output=True,text=True,timeout=60)
    (out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run(['vvp',str(out/'video.sim')],cwd=out,capture_output=True,text=True,timeout=90)
    (out/'simulation.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
    if 'PASS:' not in r.stdout:raise ValueError('No UI video pass marker')
    (out/'receipt.json').write_text(json.dumps({'result':'passed','scope':'Actual Sega pause/error raster, real Chinese bitmap ROM and native bypass patterns; no game CPU/card/device',
        'menu_geometry':[256,240],'scaler_slot':5,'inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();run(a.build,a.out)
