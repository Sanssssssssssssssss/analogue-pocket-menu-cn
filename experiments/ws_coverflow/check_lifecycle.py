#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate controller/Stop-save advertisement checks from the actual top."""
import argparse,importlib.util,shutil
from pathlib import Path
_s=importlib.util.spec_from_file_location('ws_lifecycle_boot',Path(__file__).with_name('check_boot.py'))
_m=importlib.util.module_from_spec(_s);_s.loader.exec_module(_m)
def prepare(candidate,page,out):
    candidate,page,out=map(lambda x:Path(x).resolve(),(candidate,page,out))
    if out.exists() or not out.is_relative_to(_m.ROOT/'.work/repair-20261115/ws'):raise ValueError('Fresh private output required')
    out.mkdir(parents=True);shutil.copy2(page,out/'child.hex')
    top=(candidate/'src/fpga/core/core_top.v').read_text(encoding='utf8')
    a=top.index('  reg [31:0] ui_registered_save_bytes=0;');b=top.index('  // End ordinary-save advertisement.',a)
    actual=top[a:b]
    tb=Path(__file__).with_name('tb_lifecycle.sv').read_text(encoding='utf8')
    tb=tb.replace('integer game;', '''wire clk_74a=clk,ui_new=new_load,ui_bound=bound,ui_reset=rst;
wire [31:0] ui_native_save=capacity;
'''+actual+'''
always @(negedge clk)if(new_load)begin
 @(negedge clk);if(ui_registered_save_bytes!=0)$fatal(1,"new load did not clear previous advertised size");
end
integer game;''')
    tb=tb.replace(' key(4);run_game;\n pause_game;', ''' key(4);run_game;
 repeat(5)@(negedge clk);
 if(ui_registered_save_bytes!=capacity)$fatal(1,"game save size not advertised");
 ready=0;repeat(20)@(negedge clk);
 if(bound || !rst || ui_registered_save_bytes!=capacity)$fatal(1,"Stop discarded save size before late host upload");
 repeat(100)@(negedge clk);
 if(ui_registered_save_bytes!=capacity)$fatal(1,"late host save size disappeared");
 ready=1;menu(0);
 if(ui_registered_save_bytes!=capacity)$fatal(1,"Run menu discarded last save size");
 key(4);run_game;
 pause_game;''',1)
    tb=tb.replace('if(reads!=9 || launches!=9','if(reads!=10 || launches!=10')
    tb=tb.replace('no automatic save retry; APF timeout holds reset','no automatic save retry; APF timeout holds reset; Stop/late-save/Run preserves size until next cartridge')
    (out/'tb.sv').write_text(tb,encoding='utf8')
    s='#!/bin/bash\nset -eu\ncd "$(dirname "$0")"\n'
    s+='iverilog -g2012 -s tb_ws_lifecycle -o probe "'+_m.wsl(out/'tb.sv')+'" "'+_m.wsl(candidate/'src/fpga/core/ws_menu.sv')+'" > build.log 2>&1\n'
    s+='vvp probe > simulation.log\ncat simulation.log\n';(out/'run.sh').write_text(s,encoding='utf8',newline='\n');return out/'run.sh'
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','page','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();print(prepare(a.candidate,a.page,a.out))
