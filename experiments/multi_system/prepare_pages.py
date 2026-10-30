#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate Chinese text data for the native RTL experiment, no game assets."""
from pathlib import Path
import argparse
import json
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from build_library import columns, font

PAGES = [
    ['选择游戏机','GBA 游戏库','FC / NES 游戏库','SFC / SNES 游戏库','','上下选择　A 进入','B 返回上级','中文前端实验'],
    ['GBA 游戏库','绿野冒险　演示一','黄金之城　演示二','星河战记　演示三','','上下选择　A 选择','B 返回机种','中文前端实验'],
    ['FC / NES 游戏库','勇者出发　演示一','城堡探险　演示二','飞行战队　演示三','','上下选择　A 选择','B 返回机种','中文前端实验'],
    ['SFC / SNES 游戏库','时光旅人　演示一','银河传说　演示二','星之勇者　演示三','','上下选择　A 选择','B 返回机种','中文前端实验'],
    ['准备游戏','','正在检查加载接口','','','B 返回机种','','中文前端实验'],
    ['暂时无法启动','','加载失败或需要系统选择','','','B 返回机种','','中文前端实验']
]


def prepare(out):
    out = Path(out)
    if out.exists(): raise ValueError('Use a new output directory')
    out.mkdir(parents=True)
    glyphs = font(); words = []
    for page in PAGES:
        for line in page:
            if line:
                width, raw, clipped, missing = columns(line, glyphs)
                assert width <= 256 and not clipped and not missing, line
                words.extend(struct.unpack('<512H', raw)[:256])
            else: words.extend([0]*256)
    (out/'pages.hex').write_text(''.join(f'{w:04x}\n' for w in words), encoding='ascii')
    (out/'pages.json').write_text(json.dumps(PAGES,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--out',required=True)
    prepare(p.parse_args().out)
