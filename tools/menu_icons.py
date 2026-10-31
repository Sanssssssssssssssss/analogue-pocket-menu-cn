# SPDX-License-Identifier: MIT
"""Original pixel illustrations for native Pocket menu covers; no runtime logic."""
from functools import lru_cache
from PIL import Image, ImageDraw

LABELS = {
    'gb': 'GB 游戏库', 'gbc': 'GBC 游戏库',
    '0.FAVORITES': '精选收藏', '1.ACT': '动作冒险', '2.STG': '射击',
    '3.FTG': '格斗', '4.RPG ARPG': '角色扮演', '5.SPORTS RACING': '体育赛车',
    '6.PUZZLE TABLE': '益智桌面', '7.STRATEGY': '策略模拟', '8.OTHER': '其他游戏',
    '9.ALL GAMES': '全量备选', '9.ADVENTURE': '冒险解谜',
    '90.Originals': '原版备选', '90.Hacks': '改版作品', '99.Versions': '备选版本',
}


def kind(name):
    name = LABELS.get(name, name)
    for word, icon in (
        ('GBC', 'gbc'), ('GBA', 'gba'), ('GB', 'gb'), ('SNES', 'snes'), ('NES', 'nes'),
        ('SFC', 'snes'), ('FC', 'nes'), ('返回', 'back'), ('格斗', 'fighting'),
        ('角色', 'rpg'), ('RPG', 'rpg'), ('射击', 'shooter'), ('动作', 'action'),
        ('冒险', 'action'), ('益智', 'puzzle'), ('体育', 'sports'), ('赛车', 'sports'),
        ('策略', 'strategy'), ('收藏', 'favorites'), ('经典', 'favorites'),
        ('宝可梦', 'pokemon'), ('塞尔达', 'action'), ('恶魔城', 'castle'),
        ('马力欧', 'mushroom'), ('最终幻想', 'rpg'), ('勇者斗恶龙', 'rpg'),
    ):
        if word in name:
            return icon
    return 'folder'


def icon_image(icon):
    """Draw at 128px, matching the actual native cover cache resolution."""
    image = Image.new('RGB', (128, 128), '#000000')
    d = ImageDraw.Draw(image)
    ink, grey, dark, gold = '#e8e6dd', '#abb1bc', '#242b36', '#d2ab55'

    def pad(x, y, color=ink):
        d.rectangle((x+5, y, x+11, y+17), fill=color)
        d.rectangle((x, y+5, x+16, y+11), fill=color)

    def button(x, y, color, r=4):
        d.ellipse((x-r, y-r, x+r, y+r), fill=color)

    if icon in ('gb', 'gbc'):
        body = '#d1d0c8' if icon == 'gb' else '#6663a6'
        screen = '#879666' if icon == 'gb' else '#69a6ae'
        d.rounded_rectangle((31, 11, 96, 115), radius=10, fill=body)
        d.rectangle((38, 21, 89, 65), fill=dark)
        d.rectangle((45, 28, 82, 57), fill=screen)
        d.rectangle((48, 31, 54, 51), fill='#a8b58a' if icon == 'gb' else '#9cc4bc')
        button(41, 43, '#cf886b', 1)
        pad(39, 77, '#30343d')
        button(78, 87, '#8b365a' if icon == 'gb' else '#d8bd70')
        button(88, 79, '#8b365a' if icon == 'gb' else '#d8bd70')
        d.line((52, 104, 60, 101), fill=dark, width=3)
        d.line((65, 104, 73, 101), fill=dark, width=3)
        for x in (79, 83, 87):
            d.line((x, 102, x+4, 109), fill=dark, width=1)
    elif icon == 'gba':
        d.rounded_rectangle((9, 34, 119, 94), radius=20, fill='#6663a6')
        d.rounded_rectangle((35, 41, 94, 87), radius=5, fill=dark)
        d.rectangle((41, 47, 87, 79), fill='#69a6ae')
        pad(14, 56, ink)
        button(104, 65, '#d8bd70', 4)
        button(112, 56, '#d8bd70', 4)
        button(23, 84, grey, 2)
        button(30, 84, grey, 2)
    elif icon == 'nes':
        d.rectangle((15, 31, 113, 79), fill=grey)
        d.rectangle((15, 31, 113, 40), fill=ink)
        d.rectangle((15, 69, 113, 79), fill='#555b66')
        d.rectangle((26, 46, 77, 64), fill=dark)
        d.rectangle((93, 41, 103, 78), fill=dark)
        d.rectangle((27, 51, 74, 53), fill=grey)
        d.rounded_rectangle((35, 85, 97, 110), radius=3, fill=ink)
        d.rectangle((38, 88, 94, 107), fill=dark)
        pad(40, 91, grey)
        button(80, 98, '#b55962', 4)
        button(90, 98, '#b55962', 4)
    elif icon == 'snes':
        d.rounded_rectangle((14, 31, 114, 86), radius=10, fill=grey)
        d.rectangle((30, 40, 96, 60), fill=ink)
        d.rectangle((35, 46, 91, 50), fill=dark)
        d.rectangle((38, 69, 50, 78), fill='#7773a8')
        d.rectangle((78, 69, 90, 78), fill='#7773a8')
        d.rounded_rectangle((27, 89, 102, 111), radius=10, fill=ink)
        pad(36, 92, dark)
        for x, y, color in ((82, 94, '#699c91'), (90, 100, '#b8a563'),
                            (82, 106, '#b56671'), (74, 100, '#7773a8')):
            button(x, y, color, 3)
    elif icon == 'back':
        d.line((85, 94, 85, 54, 43, 54), fill=grey, width=9)
        d.polygon(((53, 33), (30, 54), (53, 75)), fill=ink)
    elif icon == 'fighting':
        d.rounded_rectangle((28, 30, 84, 81), radius=14, fill='#b56671')
        d.rounded_rectangle((77, 51, 100, 87), radius=10, fill='#b56671')
        d.rectangle((38, 80, 85, 103), fill=ink)
        d.rectangle((42, 84, 81, 88), fill=grey)
        d.line((41, 37, 67, 37), fill='#d39496', width=3)
    elif icon in ('action', 'rpg'):
        d.polygon(((77, 19), (91, 19), (91, 33), (51, 74), (40, 63)), fill=ink)
        d.line((80, 26, 46, 66), fill='#899b9d', width=3)
        d.line((30, 57, 59, 84), fill=gold, width=8)
        d.line((40, 75, 25, 94), fill='#987552', width=9)
        if icon == 'rpg':
            d.polygon(((81, 72), (104, 82), (98, 105), (81, 115), (64, 105), (58, 82)), fill='#7773a8')
            d.line((81, 79, 81, 106), fill=ink, width=3)
    elif icon == 'pokemon':
        d.ellipse((25, 25, 103, 103), fill=ink)
        d.pieslice((25, 25, 103, 103), 180, 360, fill='#b56671')
        d.rectangle((25, 60, 103, 68), fill=dark)
        button(64, 64, dark, 15)
        button(64, 64, ink, 9)
        button(64, 64, grey, 4)
    elif icon == 'castle':
        for x in (23, 51, 79):
            d.rectangle((x, 42, x+26, 105), fill='#7773a8')
            d.rectangle((x, 31, x+8, 50), fill='#a8a3cb')
            d.rectangle((x+18, 31, x+26, 50), fill='#a8a3cb')
        d.rounded_rectangle((54, 75, 74, 114), radius=10, fill=dark)
    elif icon == 'mushroom':
        d.rounded_rectangle((43, 66, 85, 104), radius=10, fill=ink)
        d.pieslice((22, 20, 106, 108), 180, 360, fill='#b56671')
        d.rectangle((22, 62, 106, 70), fill='#b56671')
        button(45, 52, ink, 11)
        button(85, 52, ink, 11)
        d.rectangle((54, 77, 57, 87), fill=dark)
        d.rectangle((72, 77, 75, 87), fill=dark)
    elif icon == 'favorites':
        d.polygon(((64, 20), (76, 47), (106, 50), (84, 71), (90, 103),
                   (64, 88), (38, 103), (44, 71), (22, 50), (52, 47)), fill=gold)
        d.line((64, 32, 64, 74), fill='#e1c988', width=3)
    elif icon == 'puzzle':
        for x, y, color in ((28, 28, '#7773a8'), (67, 28, '#69a6ae'),
                            (28, 67, '#d2ab55'), (67, 67, '#b56671')):
            d.rectangle((x, y, x+32, y+32), fill=color)
            d.rectangle((x+5, y+5, x+27, y+9), fill=ink)
    elif icon == 'shooter':
        d.polygon(((64, 18), (78, 61), (102, 85), (73, 80), (64, 103),
                   (55, 80), (26, 85), (50, 61)), fill='#69a6ae')
        d.rectangle((60, 44, 68, 69), fill=ink)
    elif icon == 'strategy':
        d.rectangle((37, 89, 91, 103), fill=gold)
        d.polygon(((43, 86), (53, 56), (47, 40), (64, 24), (82, 40), (76, 56), (85, 86)), fill=ink)
        d.line((48, 80, 80, 80), fill=grey, width=3)
    elif icon == 'sports':
        d.ellipse((23, 23, 105, 105), fill='#69a6ae', outline=ink, width=4)
        d.polygon(((64, 43), (83, 57), (76, 79), (52, 79), (45, 57)), fill=dark)
        for a, b in (((64, 43), (64, 25)), ((83, 57), (102, 51)),
                     ((76, 79), (88, 96)), ((52, 79), (40, 96)), ((45, 57), (26, 51))):
            d.line((*a, *b), fill=ink, width=3)
    else:
        d.rectangle((23, 42, 105, 99), fill=gold)
        d.rectangle((23, 31, 59, 47), fill=gold)
        d.rectangle((27, 46, 101, 49), fill='#e1c988')
    return image


@lru_cache(maxsize=24)
def cover_bytes(icon):
    import struct
    image = icon_image(icon)
    result = bytearray()
    for size in (128, 80):
        for r, g, b in image.resize((size, size), Image.Resampling.NEAREST).get_flattened_data():
            result.extend(struct.pack('<H', ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)))
    return bytes(result)
