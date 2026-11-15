# SPDX-License-Identifier: MIT
"""Provide the CPS open-path word before the SPI command module samples it."""
from pathlib import Path

def patch(root,core):
    path=Path(root)/f'cores/{core}/pocket/coverflow/cps2_menu.sv'
    text=path.read_text(encoding='utf8')
    old='        if(bridge_rd) param_rd_data<=param_index==64 ? open_flags : param_index==65 ? open_size : root_path ? root_q : param_q;'
    if text.count(old)!=1:raise ValueError('CPS parameter pipeline source changed')
    text=text.replace(old,'''        // The native command bridge samples this word on bridge_rd itself.
        // SPI holds its address while the read strobe crosses to clk_rom, so
        // both synchronous RAM stages can settle before that sampling edge.
        param_rd_data<=param_index==64 ? open_flags : param_index==65 ? open_size : root_path ? root_q : param_q;''')
    path.write_text(text,encoding='utf8',newline='\n')
