#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise actual WS save FIFO and SDRAM controller at native clock rates."""
import argparse,importlib.util,re
from pathlib import Path
_s=importlib.util.spec_from_file_location('ws_boot_transfer',Path(__file__).with_name('check_boot.py'))
_m=importlib.util.module_from_spec(_s);_s.loader.exec_module(_m)
def prepare(candidate,out,intel_model):
    candidate,out,intel_model=map(lambda x:Path(x).resolve(),(candidate,out,intel_model))
    if out.exists() or not out.is_relative_to(_m.ROOT/'.work/repair-20261115/ws'):raise ValueError('Fresh private test output required')
    out.mkdir(parents=True);core=candidate/'src/fpga/core'
    # Split the physical inout for Verilator. The SDRAM state machine, request
    # acknowledgments, refresh and data timing remain the actual native source.
    rtl=(core/'rtl/sdram.sv').read_text(encoding='utf8')
    assert rtl.count("SDRAM_DQ <= 16'bZ;")==1
    rtl=rtl.replace('inout  reg [15:0] SDRAM_DQ','input [15:0] SDRAM_IN,\n\toutput reg [15:0] SDRAM_DQ').replace("SDRAM_DQ <= 16'bZ;","SDRAM_DQ <= 16'd0;").replace('dq_reg <= SDRAM_DQ;','dq_reg <= SDRAM_IN;')
    rtl=rtl.replace('reg [13:0] refresh_count','reg [3:0] state=STATE_STARTUP;\nreg [13:0] refresh_count').replace('\treg  [3:0] state = STATE_STARTUP;','')
    (out/'sdram_bus_model.sv').write_text(rtl,encoding='utf8')
    delays=re.findall(r'\.READ_MEM_CLOCK_DELAY\((\d+)\)',(core/'core_top.v').read_text(encoding='utf8'))
    if len(delays)!=1:raise ValueError('Native save upload timing changed')
    tb=Path(__file__).with_name('tb_transfer.sv').read_text(encoding='utf8').replace('.READ_MEM_CLOCK_DELAY(9)',f'.READ_MEM_CLOCK_DELAY({delays[0]})')
    wrapper=(core/'wonderswan.sv').read_text(encoding='utf8')
    tb=tb.replace('@NATIVE_RTC@',wrapper[wrapper.index('  reg rtc_cart_prev=0;'):wrapper.index('\nendmodule')])
    (out/'tb.sv').write_text(tb,encoding='utf8')
    files=[core/p for p in ('ws_data_loader.sv','data_unloader.sv')]+[out/'sdram_bus_model.sv',intel_model,out/'tb.sv']
    s='#!/bin/bash\nset -eu\nulimit -c 0\ncd "$(dirname "$0")"\n'
    s+='verilator --binary --timing --top-module tb_ws_transfer --build-jobs 2 -Wno-fatal --Mdir obj -o probe '
    s+=' '.join('"'+_m.wsl(p)+'"' for p in files)+' > build.log 2>&1\n'
    s+='./obj/probe > simulation.log 2>&1\ncat simulation.log\n'
    (out/'run.sh').write_text(s,encoding='utf8',newline='\n');return out/'run.sh'
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','out','intel-model'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();print(prepare(a.candidate,a.out,a.intel_model))
