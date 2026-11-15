#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check every menu/game pixel in the bounded GBA slide candidate."""
import argparse,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def run(out,preview=False):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'.work'):raise ValueError('Fresh .work output required')
    out.mkdir(parents=True);(out/'gba_menu_error.hex').write_text('0000000000000000\n'*240)
    if preview:
        from library import frame,rgb565
        entries=[{'title':title,'folder':True} for title in ['精选收藏','塞尔达传说','宝可梦','返回首页']]
        for n in range(3):
            raw=rgb565(frame(entries,n));values=[]
            for i in range(0,len(raw),2):
                p=int.from_bytes(raw[i:i+2],'little')
                values.append(((p>>11)<<13)|(((p>>15)&1)<<12)|(((p>>5)&63)<<6)|((p&31)<<1)|((p>>4)&1))
            (out/f'page{n+1}.hex').write_text(''.join(f'{v:05x}\n' for v in values))
    inputs=[HERE/'gba_motion_video.sv',HERE/'tb_motion.sv']
    input_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    r=subprocess.run(['iverilog','-g2012','-s','tb_motion','-o',str(out/'motion.sim'),*map(str,inputs)],capture_output=True,text=True,timeout=60)
    (out/'build.log').write_text(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run(['vvp',str(out/'motion.sim')]+(['+real_pages'] if preview else []),cwd=out,capture_output=True,text=True,timeout=600)
    (out/'simulation.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr,flush=True);r.check_returncode()
    if 'PASS:' not in r.stdout:raise ValueError('Missing motion pass marker')
    receipt={'scope':'Actual raster/cache RTL, inferred RAM; synthetic page writes, no APF/FIFO/CPU/physical device',
        'result':'passed','native_page_preview':preview,'menu_colors':'RGB565 cache is lossless for the current fixed-layout pages',
        'game_colors':'all 18 framebuffer bits retained; 38400 compared pixels',
        'inputs':input_hashes}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if preview:
        from PIL import Image
        images=[]
        for n in range(11):
            with Image.open(out/f'frame-{n}.ppm') as im:images.append(im.resize((720,480),Image.Resampling.NEAREST).copy())
        images[0].save(out/'menu-slide.gif',save_all=True,append_images=images[1:],duration=[500,180]+[17]*8+[600],loop=0)
        images[5].save(out/'menu-slide-mid.png')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--preview',action='store_true');a=p.parse_args();run(a.out,a.preview)
