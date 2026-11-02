#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Sample every numerical CoverFlow pose from the actual frozen RTL in Icarus."""
import argparse,hashlib,json,re,shutil,subprocess
from pathlib import Path
from prepare_geometry import ROOT,SOURCE,geometry
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--table',required=True);a=p.parse_args()
out,table=Path(a.out).resolve(),Path(a.table).resolve()
if out.exists() or not out.is_relative_to(ROOT/'.work') or table.exists():raise ValueError('Fresh work directory and table required')
geometry();out.mkdir(parents=True)
for name in ['font_cn.hex','font5x7.hex','font_cn_width.hex','font5x7_width.hex']:shutil.copy2(ROOT/'core/src'/name,out/name)
template=(HERE/'tb_geometry.sv').read_text();start=template.index('    cover_picker #');end=template.index('    genvar g;',start)
tb='''`timescale 1ns/1ps
module tb_dump_poses;
reg clk=0;always #5 clk=~clk;
reg moving=0,direction=0;reg [3:0] frame_number=0;
'''+template[start:end]+'''
integer p,j;reg [95:0] word;
initial begin
force reference.count=5;force reference.idx=0;force reference.frame_tick=0;
force reference.ago=0;force reference.anim=moving;force reference.adir=direction;force reference.af=frame_number;
repeat(200)@(negedge clk);
for(p=0;p<17;p=p+1)begin
 moving=p!=0;direction=p>=9;frame_number=p==0 ? 0:p>=9 ? p-9:p-1;
 repeat(4)@(negedge clk);
 for(j=0;j<4;j=j+1)word[j*24+:24]={reference.cx[j],reference.cs[j],reference.cb[j]};
 $display("POSE %0d %024h",p,word);
end
$finish;end
endmodule
'''
(out/'tb_dump_poses.sv').write_text(tb)
inputs=[SOURCE,HERE/'sim_ram.sv',out/'tb_dump_poses.sv']
r=subprocess.run(['iverilog','-g2012','-s','tb_dump_poses','-o',str(out/'poses.sim'),*map(str,inputs)],capture_output=True,text=True,timeout=60)
(out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
r=subprocess.run(['vvp',str(out/'poses.sim')],cwd=out,capture_output=True,text=True,timeout=60)
(out/'simulation.log').write_text(r.stdout+r.stderr);r.check_returncode()
rows=[{'index':int(n),'word':word} for n,word in re.findall(r'^POSE (\d+) ([0-9a-f]{24})$',r.stdout,re.M)]
if [x['index'] for x in rows]!=list(range(17)):raise ValueError('Missing/unknown pose data')
result={'source':'core/src/core/cover_picker.sv','source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'scope':'Actual frozen RTL numeric x/size/brightness outputs: rest, eight right and eight left poses; no game CPU/card/hardware',
    'engine':'Icarus; source control disabled, count 5 and animation state supplied; numerical geometry independent of cache RAM',
    'layout':'96 bits, slot k in bits k*24+:24, {signed x[10:0],size[7:0],brightness[4:0]}','poses':rows}
table.parent.mkdir(parents=True,exist_ok=True);table.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'poses':len(rows),'table':str(table)}))
