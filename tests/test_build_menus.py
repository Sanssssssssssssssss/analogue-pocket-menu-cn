# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_library
import build_menus
import delivery
from sega_formats import legacy_gamegear


def put(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)


def gba_rom(tag=0):
    raw=bytearray(32768);raw[0xA0:0xAC]=b'LAB FIXTURE '
    raw[0xAC:0xB0]=b'TEST';raw[0xB2]=0x96
    raw[0xBD]=(-sum(raw[0xA0:0xBD])-0x19)&255;raw[-1]=tag
    return raw


def snapshot(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def entries(folder):
    manifest=delivery.read(folder/'library-manifest.json');result={};pages={}
    for item in manifest['files']:
        if not item['path'].startswith('Assets/') or not item['path'].endswith('.bin') or 'bios' in item['path']:continue
        raw=(folder/item['path']).read_bytes();page=[]
        if raw[:4]==b'GBCV':
            count=struct.unpack_from('<H',raw,6)[0];art=528+count*128;paths=art+count*65536
            for i in range(count):
                row=raw[528+i*128:528+(i+1)*128];path=raw[paths+i*768:paths+i*768+256].split(b'\0')[0].decode('utf8')
                if not row[40]&128:result[path]=(raw[art+i*65536+45568:art+i*65536+46592],row)
        else:
            count,art=struct.unpack_from('<II',raw,8)
            for i in range(count):
                row=raw[64+i*1024:64+(i+1)*1024];path=row[32:288].split(b'\0')[0].decode('utf8')
                if row[4]:page.append(path)
                else:result[path]=(raw[art+i*65536+45568:art+i*65536+46592],row)
        pages['/'+item['path']]=(count,page)
    return result,pages


class FilenameMenus(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.card=self.root/'card'
        put(self.card/'Analogue_Pocket.json',b'{"product":"Analogue Pocket"}')
        put(self.card/'Saves/gba/common/important.sav',b'Important fixture progress')

    def test_all_six_formats_show_unfamiliar_filenames_without_aliases_or_covers(self):
        paths={
            'GB-GBC':['Assets/gb/common/陌生冒险 甲.gb','Assets/gbc/common/自定义彩色_日本語.gbc'],
            'GBA':['Assets/gba/common/新手旅程.gba'],'NES':['Assets/nes/common/未知红白机.nes'],
            'GG':['Assets/gg/common/星の冒険.gg'],'SMS':['Assets/sms/common/My Own Adventure.sms'],
            'SG1000':['Assets/sg1000/common/我的早期主机.sg']}
        for system,names in paths.items():
            for rel in names:
                if system=='GBA':raw=gba_rom()
                elif system=='NES':raw=b'NES\x1a'+bytes([1])+bytes(11)+bytes(16384)
                else:raw=bytes(32768)
                put(self.card/rel,raw)
        before=snapshot(self.card)
        result=build_menus.build(self.card,self.root/'out')
        self.assertEqual(set(result['systems']),set(paths));self.assertEqual(before,snapshot(self.card))
        for system,names in paths.items():
            games,_=entries(self.root/'out/libraries'/system)
            self.assertEqual(set(games),{'/'+r for r in names})
            for rel in names:
                self.assertEqual(games['/'+rel][0],build_library.columns(Path(rel).stem,build_library.font())[1])
        gba_manifest=delivery.read(self.root/'out/libraries/GBA/library-manifest.json')
        self.assertEqual(gba_manifest['covers']['missing_entry_references'],1)

    def test_gba_flat_folder_with_129_roms_is_automatically_paged_for_f2(self):
        for i in range(129):put(self.card/f'Assets/gba/common/Unknown {i:03}.gba',gba_rom(i))
        before=snapshot(self.card)
        build_menus.build(self.card,self.root/'out')
        games,pages=entries(self.root/'out/libraries/GBA')
        self.assertEqual(len(games),129);self.assertTrue(all(n<=128 for n,_ in pages.values()))
        self.assertGreaterEqual(len(pages),4)
        pending=['/Assets/gbalab/common/menu.bin'];seen=set()
        while pending:
            name=pending.pop()
            if name in seen:continue
            seen.add(name);pending.extend(pages[name][1])
        self.assertEqual(seen,set(pages));self.assertEqual(before,snapshot(self.card))

    def test_gba_paged_folders_keep_back_links_and_generated_chinese_labels(self):
        for i in range(4):put(self.card/f'Assets/gba/common/目录{i}/自己的游戏.gba',gba_rom(i))
        put(self.card/'Assets/gba/common/目录0/子目录/另一个.gba',gba_rom(5))
        with delivery.imports():
            f1=delivery.module('experiments/gba_menu/library.py');f2=delivery.module('experiments/gba_coverflow/library.py')
            manifest=f1.build(self.card,self.root/'f1',page_limit=4)
            self.assertTrue(any('第 ' in title for title in manifest['page_titles'].values()))
            f2.upgrade(self.root/'f1',self.root/'f2')
        games,pages=entries(self.root/'f2');self.assertEqual(len(games),5)
        self.assertTrue(all(n<=4 for n,_ in pages.values()))
        for _,links in pages.values():self.assertTrue(set(links).issubset(pages))

    def test_rename_add_remove_rebuild_updates_filename_and_retains_save_identity(self):
        old=self.card/'Assets/gba/common/旧名字.gba';put(old,gba_rom())
        first=self.root/'first';build_menus.build(self.card,first)
        old_games,_=entries(first/'libraries/GBA');old_row=old_games['/Assets/gba/common/旧名字.gba'][1]
        new=old.with_name('新名字.gba');old.rename(new)
        put(self.card/'Assets/gba/common/新增.gba',gba_rom(1))
        before=snapshot(self.card);build_menus.build(self.card,self.root/'second')
        games,_=entries(self.root/'second/libraries/GBA')
        self.assertEqual(set(games),{'/Assets/gba/common/新名字.gba','/Assets/gba/common/新增.gba'})
        self.assertEqual(games['/Assets/gba/common/新名字.gba'][1][288:800],old_row[288:800])
        self.assertEqual(games['/Assets/gba/common/新名字.gba'][0],build_library.columns('新名字',build_library.font())[1])
        self.assertEqual(before,snapshot(self.card))

    def test_optional_alias_missing_art_and_invalid_gba_are_reported_without_source_writes(self):
        put(self.card/'Assets/gba/common/Unknown.gba',gba_rom())
        put(self.card/'Assets/gba/common/Broken.gba',b'bad header')
        aliases=self.root/'names.json';delivery.write(aliases,{'Assets/gba/common/Unknown.gba':'我的标题'})
        covers=self.root/'empty-covers';covers.mkdir();before=snapshot(self.card)
        result=build_menus.build(self.card,self.root/'out',titles=aliases,covers=covers,skip_invalid=True)
        self.assertEqual(result['systems']['GBA']['excluded'],1)
        games,_=entries(self.root/'out/libraries/GBA')
        self.assertEqual(games['/Assets/gba/common/Unknown.gba'][0],build_library.columns('我的标题',build_library.font())[1])
        self.assertEqual(before,snapshot(self.card))

    def test_output_on_input_and_unknown_alias_are_rejected(self):
        put(self.card/'Assets/gba/common/Own.gba',gba_rom());before=snapshot(self.card)
        with self.assertRaises(ValueError):build_menus.build(self.card,self.card/'generated')
        aliases=self.root/'names.json';delivery.write(aliases,{'Assets/gba/common/Missing.gba':'不存在'})
        with self.assertRaises(ValueError):build_menus.build(self.card,self.root/'out',titles=aliases)
        self.assertFalse((self.root/'out').exists());self.assertEqual(before,snapshot(self.card))

    def test_legacy_gamegear_sms_extension_uses_content_and_preserves_names(self):
        raw=bytearray(32768);raw[0x7ff0:0x7ff8]=b'TMR SEGA';raw[0x7fff]=0x60
        path='Assets/gg/common/自己的GG游戏.sms';put(self.card/path,raw)
        raw[0x7fff]=0x40;put(self.card/'Assets/gg/common/Actual SMS.sms',raw)
        before=snapshot(self.card);result=build_menus.build(self.card,self.root/'out')
        games,_=entries(self.root/'out/libraries/GG')
        self.assertEqual(set(games),{'/'+path});self.assertEqual(before,snapshot(self.card))
        self.assertEqual(result['systems']['GG']['excluded'],1)
        self.assertFalse(legacy_gamegear(bytes(524288)))
        self.assertFalse(legacy_gamegear(bytes(512)+bytes(raw)))


if __name__=='__main__':unittest.main()
