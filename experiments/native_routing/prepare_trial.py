#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare isolated no-game trial sources with silent audio and explicit APF I/O exceptions."""
import argparse
from prepare_probe import prepare

def trial(archive,out):
    out=prepare(archive,out)
    for name in ['A','B']:
        fpga=out/name/'src/fpga';p=fpga/'core/core_top.v';text=p.read_text(encoding='utf8')
        start=text.index('assign audio_mclk = audgen_mclk;')
        end=text.index('///////////////////////////////////////////////',start)
        text=text[:start]+'assign audio_mclk = 0;\nassign audio_lrck = 0;\nassign audio_dac = 0;\n\n'+text[end:]
        p.write_text(text,encoding='utf8',newline='\n')
        (fpga/'core/core_constraints.sdc').write_text('''# Internal clocks are analyzed; external APF protocol I/O is explicitly excepted.
# I/O exceptions follow the existing GBA project; they are not board setup/hold signoff.
set_clock_groups -asynchronous \\
 -group {bridge_spiclk} -group {clk_74a} -group {clk_74b} \\
 -group {ic|mp1|mf_pllbase_inst|altera_pll_i|general[0].gpll~PLL_OUTPUT_COUNTER|divclk ic|mp1|mf_pllbase_inst|altera_pll_i|general[1].gpll~PLL_OUTPUT_COUNTER|divclk}
derive_clock_uncertainty
set_false_path -from [get_ports {bridge_1wire bridge_spimiso bridge_spimosi bridge_spiss}]
set_false_path -to [get_ports {bridge_1wire bridge_spimiso bridge_spimosi scal_auddac scal_audlrck scal_audmclk scal_clk scal_de scal_hs scal_skip scal_vid[*] scal_vs}]
''',encoding='utf8',newline='\n')
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['archive','out']:p.add_argument('--'+name,required=True)
    a=p.parse_args();print(trial(a.archive,a.out))
