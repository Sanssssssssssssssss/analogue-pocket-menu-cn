#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare the animation candidate's game output to a separate accepted adapter."""
import argparse,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline-adapter',required=True);p.add_argument('--out',required=True);a=p.parse_args()
out=Path(a.out).resolve();baseline=Path(a.baseline_adapter).resolve()
if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
raw=baseline.read_text(encoding='utf8')
accepted=json.loads((HERE/'evidence/ownership-build.json').read_text(encoding='utf8'))
if hashlib.sha256(baseline.read_bytes()).hexdigest()!=accepted['source_files']['src/fpga/core/video_adapter.sv']:
    raise ValueError('Baseline differs from the recorded 0.2.0-gba.3 adapter')
if raw.count('module video_adapter (')!=1:raise ValueError('Expected accepted video adapter source')
out.mkdir(parents=True);(out/'gba_menu_error.hex').write_text('0000000000000000\n'*240)
(out/'reference.sv').write_text(raw.replace('module video_adapter (','module video_reference (').replace('localparam int unsigned','localparam integer'))
inputs=[HERE/'gba_motion_video.sv',HERE/'tb_game_video.sv',baseline]
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
r=subprocess.run(['iverilog','-g2012','-s','tb_game_video','-o',str(out/'game.sim'),str(inputs[0]),str(inputs[1]),str(out/'reference.sv')],capture_output=True,text=True,timeout=60)
(out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
r=subprocess.run(['vvp',str(out/'game.sim')],cwd=out,capture_output=True,text=True,timeout=180)
(out/'simulation.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr,flush=True);r.check_returncode()
if 'PASS:' not in r.stdout:raise ValueError('Missing raster pass marker')
(out/'receipt.json').write_text(json.dumps({'result':'passed','scope':'Candidate and separately supplied accepted adapter RTL; inferred RAM, synthetic GPU writes, no CPU/device',
    'baseline_version':accepted['version'],
    'clock_samples':280896,'game_pixels':76800,'compared':['RGB','data enable','HS','VS','scaler skip'],'inputs':hashes},indent=2)+'\n')
