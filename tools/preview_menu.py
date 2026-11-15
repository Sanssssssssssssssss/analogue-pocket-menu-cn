#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare an exact v9 page for native RTL preview; run with Verilator on Linux/WSL."""
import argparse
from pathlib import Path
import shutil

from build_library import ROOT
from style_library import decode


def prepare(pack, out, views):
    pack, out = Path(pack).resolve(), Path(out).resolve()
    raw = pack.read_bytes()
    count = len(decode(raw)['entries'])
    if out.exists() or len(raw)>1048576 or not 1<=views<=min(4,count):
        raise ValueError('Use a new output folder, a page of at most 1 MiB and 1..4 existing views')
    if not out.is_relative_to(ROOT/'.work'):
        raise ValueError('Preview output must be under the project .work folder')
    out.mkdir(parents=True)
    (out/'covers7.hex').write_text(''.join(f'{b:02x}\n' for b in raw),encoding='ascii')
    for name in ('font_cn.hex','font_cn_width.hex','font5x7.hex','font5x7_width.hex'):
        shutil.copy2(ROOT/'core/src'/name,out/name)
    tb=(ROOT/'core/tools/sim/tb_stream.sv').read_text()
    tb=tb.replace('module tb_stream;','module tb_icons;').replace('.CB(3)','.CB(7)')
    tb=tb.replace('sl = g % 8;','sl = g % 128;')
    tb=tb.replace(".dbg(16'hA5C3),", ".dbg(16'd0), .cart_notify(32'd0), .cart_play(1'b0), .cprobe_done(1'b0), .cart_hdr(224'd0),")
    start=tb.index('  // capture hi-res frames')
    end=tb.index('  integer errors = 0;',start)
    tb=tb[:start]+r'''
  integer f=0, pixels=0; reg capture=0;
  always @(negedge clk_vid) if(capture && hr_de) begin
    $fwrite(f,"%c%c%c",hr_rgb[23:16],hr_rgb[15:8],hr_rgb[7:0]); pixels=pixels+1;
  end
  task shot(input integer number);
    reg [8*64-1:0] filename;
    begin
      wait(dut.state==23 && dut.level==8 && !dut.anim && dut.idx==number);
      repeat(14) @(posedge hr_vs);
      check_cache;
      if(errors || collide) $fatal(1,"cover cache mismatch");
      @(posedge hr_vs);
      $sformat(filename,"view-%0d.ppm",number);f=$fopen(filename,"wb");
      $fwrite(f,"P6\n320 288\n255\n");pixels=0;capture=1;
      @(posedge hr_vs);capture=0;$fclose(f);
      if(pixels!=320*288 || !hr_mode || !hold_gb) $fatal(1,"invalid menu frame");
    end
  endtask
''' +tb[end:]
    start=tb.index('  initial begin\n    force dut.boot_timer')
    tb=tb[:start]+f'''
  integer view;
  initial begin
    force dut.boot_timer=27'd36_999_990; #100 core_ready=1; #2000 release dut.boot_timer;
    wait(dut.state==23 && dut.level==8);
    if(dut.count!={count}) $fatal(1,"wrong page count");
    for(view=0;view<{views};view=view+1) begin
      if(view!=0) begin
        @(negedge clk);cont1_key=8;repeat(2) @(posedge hr_vs);@(negedge clk);cont1_key=0;
      end
      shot(view);
    end
    $display("RESULT PASS: {views} exact native menu frames; APF/SDRAM models, no game execution");
    $finish;
  end
  initial begin #4000000000; $fatal(1,"preview timeout state=%0d idx=%0d",dut.state,dut.idx); end
endmodule
'''
    (out/'tb_icons.sv').write_text(tb,encoding='utf-8')
    script='''#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
project=$(CDPATH= cd -- "../../.." && pwd)
verilator --binary --timing -Wno-fatal -j 2 --top-module tb_icons --Mdir obj \\
  tb_icons.sv "$project/core/src/core/cover_picker.sv" "$project/core/tools/sim/dpram_sim.v" > build.log 2>&1
./obj/Vtb_icons > simulation.log 2>&1
tail -n 3 simulation.log
'''
    # Resolve from the actual depth; generated script remains local to this checkout.
    script=script.replace('"../../.."', '"'+Path(*(['..']*len(out.relative_to(ROOT).parts))).as_posix()+'"')
    (out/'run.sh').write_text(script,encoding='utf-8',newline='\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pack',required=True);p.add_argument('--out',required=True)
    p.add_argument('--views',type=int,default=2);a=p.parse_args()
    try: print(prepare(a.pack,a.out,a.views))
    except (OSError,ValueError) as error:p.exit(2,str(error)+'\n')
