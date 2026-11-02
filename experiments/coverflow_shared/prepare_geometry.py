#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Extract the accepted GB/GBC CoverFlow geometry without changing frozen inputs."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'core/src/core/cover_picker.sv'

def geometry(compact=False):
    records=json.loads((ROOT/'docs/build/source-inputs.json').read_text(encoding='utf8'))['files']
    expected=next(r['sha256'] for r in records if r['path']=='core/cover_picker.sv')
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Accepted CoverFlow source changed')
    s=raw.decode('utf8');start=s.index('localparam AN = 8;');end=s.index('// position bar thumb:',start)
    original=s[start:end]
    # Soft reset is the only state adaptation. Geometry/functions remain verbatim.
    body=original.replace('    if (ago) begin anim <= 1; af <= 0; adir <= ago_dir; end',
        '    if (!enable) begin anim <= 0; af <= 0; adir <= 0; end\n    else if (ago) begin anim <= 1; af <= 0; adir <= ago_dir; end',1)
    body=body.replace('    if (frame_tick) begin\n        if (tlevel',
        '    if (!enable) tlevel <= 0;\n    else if (frame_tick) begin\n        if (tlevel',1)
    if body==original:raise ValueError('Geometry reset anchor changed')
    prefix='''// SPDX-License-Identifier: MIT
// Geometry copied from the accepted maxsorto/Pocket Lab CoverFlow; original
// attribution is retained by the source repository and LICENSE.md.
module coverflow_geometry (
    input wire clk_74a,enable,frame_tick,ago,ago_dir,
    input wire [3:0] tl_target,
    input wire [10:0] rcount,
    input wire [10:0] cgame[0:4],
    output reg anim=0,adir=0,
    output reg [3:0] af=0,tlevel=0,
    output wire signed [10:0] x[0:3],
    output wire [7:0] size[0:3],
    output wire [4:0] brightness[0:3],
    output wire [10:0] game[0:3],
    output wire valid[0:3]
);
reg [10:0] cg[0:3];
'''
    suffix='''genvar g;
generate for(g=0;g<4;g=g+1)begin:outputs
    assign x[g]=cx[g];assign size[g]=cs[g];assign brightness[g]=cb[g];
    assign game[g]=cg[g];assign valid[g]=cv[g];
end endgenerate
endmodule
'''
    table_hash=None
    if compact:
        table=Path(__file__).with_name('geometry_poses.json')
        data=json.loads(table.read_text(encoding='utf8'))
        if data['source_sha256']!=expected or [p['index'] for p in data['poses']]!=list(range(17)):raise ValueError('Numerical pose table source differs')
        animation=body[:body.index('function [8:0] ease')]
        constants='\n'.join(f"        5'd{p['index']}:pose_data=96'h{p['word']};" for p in data['poses'])
        body=animation+'''// Values sampled from the actual frozen RTL, not a new easing curve.
function [95:0] pose_data(input [4:0] n);
    case(n)
'''+constants+'''
        default:pose_data=96'h'''+data['poses'][0]['word']+''';
    endcase
endfunction
wire [2:0] pose_frame=af>=7 ? 3'd7:af[2:0];
wire [4:0] pose_index=anim ? (adir ? 5'd9:5'd1)+{2'd0,pose_frame}:5'd0;
wire [95:0] pose_word=pose_data(pose_index);
reg signed [10:0] cx[0:3];reg [7:0] cs[0:3];reg [4:0] cb[0:3];reg cv[0:3];
integer ki;
always @(posedge clk_74a)for(ki=0;ki<4;ki=ki+1)begin:cover_pose
    reg signed [2:0] ts;
    ts=(anim && !adir) ? ki-2:ki-1;
    {cx[ki],cs[ki],cb[ki]}<=pose_word[ki*24+:24];
    case(ts)3'sd0:cg[ki]<=cgame[0];3'sd1:cg[ki]<=cgame[1];-3'sd1:cg[ki]<=cgame[2];
        3'sd2:cg[ki]<=cgame[3];default:cg[ki]<=cgame[4];endcase
    cv[ki]<=(rcount>1 || ts==0) && (anim || ki!=3) && pose_word[ki*24+:5]!=0;
end
'''
        table_hash=hashlib.sha256(table.read_bytes()).hexdigest()
    return prefix+body+suffix,{'source':'core/src/core/cover_picker.sv','source_sha256':expected,
        'verbatim_geometry_sha256':hashlib.sha256(original.encode()).hexdigest(),
        'compact':compact,'pose_table_sha256':table_hash,
        'adaptation':'Numerical poses from original RTL table; original state/title timing and game/valid mapping retained' if compact else 'Ports and explicit disabled-state animation/title reset only; original geometry/easing/slot sizes/brightness retained'}

def prepare(out,compact=False):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Use fresh .work output')
    out.mkdir(parents=True);code,record=geometry(compact)
    (out/'coverflow_geometry.sv').write_text(code,encoding='utf8',newline='\n')
    (out/'geometry-source.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--compact',action='store_true');a=p.parse_args();print(prepare(a.out,a.compact))
