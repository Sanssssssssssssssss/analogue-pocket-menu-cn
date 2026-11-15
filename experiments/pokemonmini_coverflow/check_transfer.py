#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build native Mini FIFO/SDRAM/EEPROM transfer simulation at real clocks."""
import argparse,importlib.util
from pathlib import Path
_s=importlib.util.spec_from_file_location('pm_boot_transfer',Path(__file__).with_name('check_boot.py'))
_m=importlib.util.module_from_spec(_s);_s.loader.exec_module(_m)
def prepare(candidate,out,intel_model):
    candidate,out,intel_model=map(lambda x:Path(x).resolve(),(candidate,out,intel_model))
    if out.exists() or not _m._prepare.private_output(out):raise ValueError('Fresh private test output required')
    out.mkdir(parents=True);core=candidate/'src/fpga/core'
    # Verilator cannot propagate the upstream procedural inout tristate. For
    # this write-only bus test, expose its output register and set undriven
    # cycles to zero. Commands, address/data timing and state machine stay exact.
    rtl=(core/'rtl/sdram.sv').read_text(encoding='utf8')
    assert rtl.count("SDRAM_DQ <= 'Z;")==1
    rtl=rtl.replace('inout  reg [15:0] SDRAM_DQ','output reg [15:0] SDRAM_DQ').replace("SDRAM_DQ <= 'Z;","SDRAM_DQ <= 16'd0;")
    # A procedure-local static initialization is supported by Quartus. Hoist
    # this equivalent declaration for Verilator's mixed-assignment restriction.
    assert rtl.count('reg init_old=0;')==1
    rtl=rtl.replace('reg [1:0] mode;','reg init_old=0;\nreg [1:0] mode;').replace('\treg init_old=0;','')
    (out/'sdram_write_model.sv').write_text(rtl,encoding='utf8')
    files=[core/p for p in ('pm_data_loader.sv','data_unloader.sv','rtl/eeprom.sv')]+[out/'sdram_write_model.sv']
    files+=[intel_model,Path(__file__).with_name('tb_transfer.sv')]
    s='#!/bin/bash\nset -eu\nulimit -c 0\ncd "$(dirname "$0")"\n'
    s+='verilator --binary --timing --top-module tb_pm_transfer --build-jobs 2 -Wno-fatal --Mdir obj -o probe '
    s+=' '.join('"'+_m.wsl(p)+'"' for p in files)+' > build.log 2>&1\n'
    s+='./obj/probe > simulation.log 2>&1\ncat simulation.log\n'
    (out/'run.sh').write_text(s,encoding='utf8',newline='\n');return out/'run.sh'
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','out','intel-model'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();print(prepare(a.candidate,a.out,a.intel_model))
