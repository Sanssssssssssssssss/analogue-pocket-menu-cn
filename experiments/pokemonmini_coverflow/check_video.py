#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare original LCD color arithmetic and actual video scan against LUT RTL."""
import argparse,hashlib,importlib.util,json,re
from pathlib import Path
spec=importlib.util.spec_from_file_location('pm_video_boot',Path(__file__).with_name('check_boot.py'))
boot=importlib.util.module_from_spec(spec);spec.loader.exec_module(boot)

def prepare(source,candidate,out):
    source,candidate,out=map(lambda p:Path(p).resolve(),(source,candidate,out))
    if out.exists() or not boot._prepare.private_output(out):raise ValueError('Fresh private Mini video test required')
    out.mkdir(parents=True)
    native=(source/'src/fpga/core/main.sv').read_text()
    changed=(candidate/'src/fpga/core/main.sv').read_text()
    prefix='''module @NAME@(input clk_sys_32,input reset,input blending_enabled,input [31:0] status,
 input frame_complete,input [5:0] lcd_contrast,input [7:0] lcd_read_column,
 output [23:0] rgb,output [3:0] syncs,output [11:0] read_address);
reg [3:0] clk_prescale=0;reg [2:0] minx_clk_prescale=0;
always @(posedge clk_sys_32)begin clk_prescale<=clk_prescale==4 ? 0:clk_prescale+1'b1;minx_clk_prescale<=minx_clk_prescale+1'b1;end
wire [7:0] video_r,video_g,video_b;wire hsync,vsync,hblank,vblank;
assign rgb={video_r,video_g,video_b};assign syncs={hsync,vsync,hblank,vblank};
assign read_address={lcd_read_ypos,lcd_read_xpos};
'''
    for name,text in [('native_video',native),('candidate_video',changed)]:
        a=text.index('  wire ce_pix');b=text.index('  // in:  {select',a)
        (out/(name+'.sv')).write_text(prefix.replace('@NAME@',name)+text[a:b]+'\nendmodule\n',encoding='utf8')
    s='''`timescale 1ns/1ps
module tb_pm_video;
reg clk=0;always #15.625002441 clk=~clk;
reg reset=1,blend=0,frame=0;reg [31:0] status=0;reg [5:0] contrast=0;reg [7:0] column=0;
wire [23:0] rgb0,rgb1;wire [3:0] sync0,sync1;wire[11:0] addr0,addr1;
native_video ref_video(clk,reset,blend,status,frame,contrast,column,rgb0,sync0,addr0);
candidate_video dut(clk,reset,blend,status,frame,contrast,column,rgb1,sync1,addr1);
integer cycles=0,frames=0,active=0,seed=32'h4b725ea1;
reg prior_vs=0;
always @(negedge clk)begin
 cycles=cycles+1;reset=cycles<32;frame=(cycles%8192)==32;
 if(frame)begin seed=seed*1664525+1013904223;contrast=seed[21:16];end
 column=(addr0[7:0]^addr0[11:4])+(cycles/8192);
 if(cycles%533170==0)begin blend=~blend;status[30]=~status[30];status[29:28]=status[29:28]==2 ? 0:status[29:28]+1'b1;end
 #1;
 if({rgb0,sync0,addr0} !== {rgb1,sync1,addr1})$fatal(1,"Native video mismatch cycle=%0d rgb=%h/%h sync=%h/%h",cycles,rgb0,rgb1,sync0,sync1);
 if(!sync0[0] && !sync0[1])active=active+1;
 if(sync0[2]&&!prior_vs)frames=frames+1;prior_vs=sync0[2];
 if(cycles==6400000)begin
  if(frames<10 || active<1000)$fatal(1,"Video did not scan");
  $display("PASS native video: %0d clocks, %0d frames, RGB/blank/sync/read-address exact; all zoom settings, blending and changing frame contrast",cycles,frames);$finish;
 end
end
integer intensity,r,g,b;
initial begin
 for(intensity=0;intensity<256;intensity=intensity+1)begin
  r=((255-intensity)*8'hb7+intensity*8'h04)/255;
  g=((255-intensity)*8'hca+intensity*8'h16)/255;
  b=((255-intensity)*8'hb7+intensity*8'h04)/255;
  if(dut.pm_lcd_color(intensity[7:0]) !== {r[7:0],g[7:0],b[7:0]})$fatal(1,"Palette mismatch intensity=%0d",intensity);
 end
 $display("PASS all 256 LCD intensities retain exact native 24-bit RGB, including endpoints and integer rounding");
end
endmodule
'''
    (out/'tb.sv').write_text(s,encoding='utf8')
    files=[out/n for n in ['native_video.sv','candidate_video.sv','tb.sv']]
    run='#!/bin/bash\nset -eu\nulimit -c 0\ncd "$(dirname "$0")"\n'
    run+='verilator --binary --timing --top-module tb_pm_video --build-jobs 2 -Wno-fatal --Mdir obj -o probe '
    run+=' '.join('"'+boot.wsl(p)+'"' for p in files)+' > build.log 2>&1\n'
    run+='./obj/probe > simulation.log 2>&1\ncat simulation.log\n'
    (out/'run.sh').write_text(run,newline='\n')
    (out/'inputs.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files+[source/'src/fpga/core/main.sv',candidate/'src/fpga/core/main.sv']},indent=2)+'\n')
    return out/'run.sh'

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','candidate','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();print(prepare(a.source,a.candidate,a.out))
