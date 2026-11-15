#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise menu lifecycle and actual APF commands; optionally actual Intel FIFO."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from prepare_test import prepare

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',required=True);p.add_argument('--out',required=True);p.add_argument('--intel-model')
a=p.parse_args();build=Path(a.build).resolve();out=prepare(a.out);here=Path(__file__).resolve().parent
core=build/'src/fpga/core';pocket=build/'src/fpga/pocket';common=build/'src/fpga/apf/common.v'
cmd=core/'core_bridge_cmd.v'
# Icarus requires omitted trailing output ports to be named explicitly.
text=cmd.read_text(encoding='utf-8').replace('synch_3 s01(bridge_endian_little, endian_little_s, clk);',
    'synch_3 s01(.i(bridge_endian_little),.o(endian_little_s),.clk(clk),.rise(),.fall());')
(out/'core_bridge_cmd.v').write_text(text)
jobs=[('tb_menu',[here/'gba_menu.sv',here/'tb_menu.sv']),
      ('tb_commands',[here/'tb_commands.sv',out/'core_bridge_cmd.v',common])]
if a.intel_model:
    jobs.append(('tb_reload',[here/'tb_reload.sv',pocket/'apf_write_ingress.sv',core/'save_type_detector.sv',core/'rtc_persistence.sv',Path(a.intel_model).resolve()]))
results=[]
for top,inputs in jobs:
    command=['iverilog','-g2012','-I',str(out),'-s',top,'-o',str(out/(top+'.sim')),*map(str,inputs)]
    r=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=60)
    (out/(top+'-build.log')).write_text(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run(['vvp',str(out/(top+'.sim'))],cwd=out,capture_output=True,text=True,timeout=60)
    (out/(top+'.log')).write_text(r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
    results.append({'test':top,'result':'passed','input_hashes':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs}})
receipt={'scope':'RTL simulation only: no physical Pocket, game CPU, PSRAM or SD durability validation',
         'tests':results,'vendor_fifo_test':bool(a.intel_model)}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
