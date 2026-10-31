#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Join real menu, APF commands, pixel FIFO and raster for first-screen checks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from prepare_test import prepare

p=argparse.ArgumentParser(description=__doc__)
for name in ('build','intel-model','out'):p.add_argument('--'+name,required=True)
p.add_argument('--fade',action='store_true',help='Probe the separate fade candidate')
a=p.parse_args();build=Path(a.build).resolve();out=prepare(a.out);here=Path(__file__).resolve().parent
page=out/'library/Assets/gbalab/common/menu.bin'
(out/'page.hex').write_text(''.join(f'{b:02x}\n' for b in page.read_bytes()))
shutil.copy2(build/'src/fpga/build/gba_menu_error.hex',out)
command=build/'src/fpga/core/core_bridge_cmd.v';video=build/'src/fpga/core/video_adapter.sv'
text=command.read_text(encoding='utf8').replace('synch_3 s01(bridge_endian_little, endian_little_s, clk);',
    'synch_3 s01(.i(bridge_endian_little),.o(endian_little_s),.clk(clk),.rise(),.fall());')
(out/'commands.v').write_text(text)
(out/'video.sv').write_text(video.read_text(encoding='utf8').replace('localparam int unsigned','localparam integer'))
ram=(here/'tb_commands.sv').read_text();start=ram.index('module mf_datatable');end=ram.index('endmodule',start)+len('endmodule')
(out/'table.sv').write_text(ram[start:end])
bench=here/'tb_boot.sv'
if a.fade:
    bench=out/'tb_boot.sv'
    bench.write_text((here/'tb_boot.sv').read_text().replace('.menu_fault(fault),','.menu_fault(fault),.menu_active(owned),'))
inputs=[bench,here/'gba_menu.sv',here/'gba_menu_pixels.sv',command,video,
        build/'src/fpga/pocket/data_loader.sv',build/'src/fpga/apf/common.v',Path(a.intel_model).resolve()]
if a.fade:inputs.append(build/'src/fpga/core/menu_fade.sv')
rtl=[out/'commands.v' if x==command else out/'video.sv' if x==video else x for x in inputs]+[out/'table.sv']
r=subprocess.run(['iverilog','-g2012','-s','tb_boot','-o',str(out/'boot.sim'),*map(str,rtl)],capture_output=True,text=True,timeout=60)
(out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
cases=[]
for name,flags in [('complete',[]),('retained-game-ownership',['+dirty_boot']),('missing-tail',['+drop_last'])]:
    r=subprocess.run(['vvp',str(out/'boot.sim'),*flags],cwd=out,capture_output=True,text=True,timeout=600)
    (out/(name+'.log')).write_text(r.stdout+r.stderr);print(r.stdout+r.stderr,flush=True);r.check_returncode()
    cases.append({'case':name,'result':'passed'})
receipt={'scope':'Actual menu/APF command/FIFO/video integration; RAM table storage, host and ready/idle inputs modeled; no GBA CPU or physical device',
         'fade_candidate':a.fade,'cases':cases,'input_hashes':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs}}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
