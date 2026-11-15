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


def sfc_rom(mode=0x20, *, ram=3, region=1, copier=0):
    raw=bytearray(131072+copier)
    pos=(0x7fc0 if mode==0x20 else 0xffc0)+copier
    raw[pos+0x15:pos+0x1b]=bytes((mode,2,7,ram,region,0x33))
    struct.pack_into('<HH',raw,pos+0x1c,0xedcb,0x1234)
    struct.pack_into('<H',raw,pos+0x3c,0x8000)
    return raw


def cps_instance(rom, buttons=0x543210):
    return {'instance':{'magic':'APF_VER_1','data_slots':[{'id':1,'filename':rom},{'id':2,'filename':'progress.sav'}],
        'memory_writes':[{'address':'0xf9000000','data':'0x8000'},{'address':'0xfc000000','data':buttons}]}}


def cps_package(root):
    """Synthetic installer fixture; contains no executable FPGA design."""
    dest = root/'core/Cores/pocketlab.CPS2'
    documents = {key: {key: {'magic':'APF_VER_1'}} for key in ('audio','data','input','interact','variants','video')}
    documents['core'] = {'core': {'magic':'APF_VER_1', 'metadata': {'author':'pocketlab','shortname':'CPS2',
        'platform_ids':['cpslab','jtcps2'],'version':'synthetic-test','date_release':'2026-11-16',
        'description':'Synthetic installer fixture','url':'https://example.com'},
        'framework':{'sleep_supported':False},'cores':[{'name':'default','id':0,'filename':'jtcps2.rbf_r'}]}}
    documents['variants']['variants']['variant_list'] = []
    documents['data']['data']['data_slots'] = [
        {'id':100,'deferload':True,'address':'0x70000000'},
        {'id':1,'deferload':True,'address':'0x00000000'},
        {'id':2,'deferload':True,'nonvolatile':True,'address':'0x00000000','size_maximum':'0x80'}, {'id':18}]
    for name,value in documents.items():
        delivery.write(dest/(name+'.json'),value)
    put(dest/'jtcps2.rbf_r',b'SYNTHETIC INSTALLER FIXTURE - NOT FPGA DATA')
    delivery.write(root/'core/Platforms/cpslab.json',{'platform':{'name':'CPS2','category':'CN Menu'}})
    put(root/'core/Platforms/_images/cpslab.bin',b'synthetic icon')
    delivery.write(root/'build-receipt.json',{'core':'pocketlab.CPS2','namespace':'cpslab',
        'menu_format':'GBAF2/jtcps2','minimum_slack_ns':0.1,'timing_records':40,
        'files':[delivery.snapshot(p,p.relative_to(root/'core').as_posix()) for p in (root/'core').rglob('*') if p.is_file()]})


def snapshot(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def entries(folder, artwork=False):
    manifest=delivery.read(folder/'library-manifest.json');result={};pages={}
    for item in manifest['files']:
        if not item['path'].startswith('Assets/') or not item['path'].endswith('.bin') or 'bios' in item['path']:continue
        raw=(folder/item['path']).read_bytes();page=[]
        if raw[:4]==b'GBCV':
            count=struct.unpack_from('<H',raw,6)[0];art=528+count*128;paths=art+count*65536
            for i in range(count):
                row=raw[528+i*128:528+(i+1)*128];path=raw[paths+i*768:paths+i*768+256].split(b'\0')[0].decode('utf8')
                if not row[40]&128:result[path]=(raw[art+i*65536:art+i*65536+45568] if artwork else raw[art+i*65536+45568:art+i*65536+46592],row)
        else:
            count,art=struct.unpack_from('<II',raw,8)
            for i in range(count):
                row=raw[64+i*1024:64+(i+1)*1024];path=row[32:288].split(b'\0')[0].decode('utf8')
                if row[4]:page.append(path)
                else:result[path]=(raw[art+i*65536:art+i*65536+45568] if artwork else raw[art+i*65536+45568:art+i*65536+46592],row)
        pages['/'+item['path']]=(count,page)
    return result,pages


class FilenameMenus(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.card=self.root/'card'
        put(self.card/'Analogue_Pocket.json',b'{"product":"Analogue Pocket"}')
        put(self.card/'Saves/gba/common/important.sav',b'Important fixture progress')

    def test_virtual_group_preserves_real_paths_saves_and_machine_modes(self):
        wrong = 'Assets/pce/common/0.FAVORITES/Wrong Series/Volleyball.pce'
        correct = 'Assets/pce/common/5.SPORTS RACING/Volleyball.pce'
        alternate_mode = 'Assets/pce/common/5.SPORTS RACING/Volleyball.sgx'
        raw = bytes(32768)
        for rel in (wrong, correct, alternate_mode):
            put(self.card/rel, raw)
        put(self.card/'Saves/pce/common/Volleyball.sav', b'Existing native progress')
        before = snapshot(self.card)
        groups = self.root/'groups.json'
        delivery.write(groups, {wrong: '5.SPORTS RACING'})
        result = build_menus.build(self.card, self.root/'grouped', ['PCE'], groups=groups)
        library = self.root/'grouped/libraries/PCE'
        manifest = delivery.read(library/'library-manifest.json')
        rows, pages = entries(library)
        self.assertEqual(set(rows), {'/'+wrong, '/'+alternate_mode})
        self.assertEqual({r['path'] for r in manifest['source_refs']}, {wrong, correct, alternate_mode})
        self.assertEqual(manifest['duplicate_menu_paths'], [correct])
        self.assertEqual(manifest['display_groups'], {wrong: '5.SPORTS RACING'})
        tag = hashlib.sha256(raw).hexdigest()[:20]
        self.assertEqual(rows['/'+wrong][1][288:544].split(b'\0')[0].decode(),
                         '/Saves/pcelab/common/'+tag+'.sav')
        self.assertEqual(snapshot(self.card), before)
        delivery.write(groups, {wrong: '../outside'})
        with self.assertRaisesRegex(ValueError, 'virtual menu folder'):
            build_menus.build(self.card, self.root/'invalid-groups', ['PCE'], groups=groups)
        self.assertEqual(snapshot(self.card), before)

    def test_gb_unsupported_size_requires_opt_in_and_keeps_originals(self):
        good = 'Assets/gb/common/Playable.gb'
        bad = 'Assets/gbc/common/Multicart.gbc'
        put(self.card/good, bytes(32768))
        put(self.card/bad, bytes(8*1024*1024+1))
        titles = self.root/'titles.json'
        delivery.write(titles, {good:'测试游戏', bad:'超出容量的合集'})
        before = snapshot(self.card)
        with self.assertRaisesRegex(ValueError, 'Unsupported ROM size'):
            build_menus.build(self.card, self.root/'strict', ['GB-GBC'], titles)
        result = build_menus.build(self.card, self.root/'filtered', ['GB-GBC'], titles, skip_invalid=True)
        library = self.root/'filtered/libraries/GB-GBC'
        manifest = delivery.read(library/'library-manifest.json')
        self.assertEqual(result['systems']['GB-GBC']['excluded'], 1)
        self.assertEqual(set(entries(library)[0]), {'/'+good})
        self.assertEqual(manifest['excluded'][0]['path'], bad)
        self.assertEqual(manifest['excluded'][0]['sha256'], before[bad])
        self.assertEqual(snapshot(self.card), before)

    def test_all_formats_show_unfamiliar_filenames_without_aliases_or_covers(self):
        paths={
            'GB-GBC':['Assets/gb/common/陌生冒险 甲.gb','Assets/gbc/common/自定义彩色_日本語.gbc'],
            'GBA':['Assets/gba/common/新手旅程.gba'],'NES':['Assets/nes/common/未知红白机.nes'],
            'GG':['Assets/gg/common/星の冒険.gg'],'SMS':['Assets/sms/common/My Own Adventure.sms'],
            'SG1000':['Assets/sg1000/common/我的早期主机.sg'],
            'PCE':['Assets/pce/common/陌生游戏🎮.pce','Assets/pce/common/陌生扩展.sgx'],
            'MD':['Assets/genesis/common/自己取得的镜像.md'],
            'SFC':['Assets/snes/common/任意名称.sfc','Assets/snes/common/带头的镜像.smc'],
            'CPS2':['Assets/jtcps2/common/陌生格斗.rom']}
        for system,names in paths.items():
            for rel in names:
                if system=='GBA':raw=gba_rom()
                elif system=='NES':raw=b'NES\x1a'+bytes([1])+bytes(11)+bytes(16384)
                elif system=='MD':raw=bytes(0x100)+b'SEGA'+bytes(32768-0x104)
                elif system=='SFC':raw=sfc_rom(0x21,copier=512) if rel.endswith('.smc') else sfc_rom()
                else:raw=bytes(32768)
                put(self.card/rel,raw)
                if system=='CPS2':
                    p=self.card/rel
                    delivery.write(p.with_suffix('.json'),cps_instance(p.name))
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
        pce_manifest=delivery.read(self.root/'out/libraries/PCE/library-manifest.json')
        self.assertTrue(any('🎮' in row.get('missing_glyphs',[]) for row in pce_manifest['warnings']))

    def test_cps2_distinguishes_variants_and_keeps_progress_after_rename(self):
        directory=self.card/'Assets/jtcps2/common'
        put(directory/'game.rom',b'\x07'*32768)
        delivery.write(directory/'first.json',cps_instance('game.rom'))
        delivery.write(directory/'second.json',cps_instance('game.rom',0x543201))
        delivery.write(directory/'unrelated.json',{'instance':[]})
        result=build_menus.build(self.card,self.root/'first',systems=['CPS2'])
        manifest=self.root/'first/libraries/CPS2/library-manifest.json'
        rows=delivery.read(manifest)['instances']
        self.assertEqual(result['systems']['CPS2']['excluded'],1)
        self.assertEqual(len({r['save_tag'] for r in rows}),2)
        save=self.card/f'Saves/cpslab/common/{rows[0]["save_tag"]}.sav'
        put(save,b'P'*128)
        (directory/'game.rom').rename(directory/'renamed.rom')
        (directory/'first.json').rename(directory/'renamed.json')
        delivery.write(directory/'renamed.json',cps_instance('renamed.rom'))
        delivery.write(directory/'second.json',cps_instance('renamed.rom',0x543201))
        before=snapshot(self.card)
        build_menus.build(self.card,self.root/'second',systems=['CPS2'])
        folder=self.root/'second/libraries/CPS2'
        refreshed=delivery.read(folder/'library-manifest.json')
        from menu_bindings import validate
        validate(folder,refreshed,'CPS2','GBAF2')
        self.assertEqual({r['save_tag'] for r in rows},{r['save_tag'] for r in refreshed['instances']})
        self.assertEqual(len([r for r in refreshed['files'] if r['path'].startswith('Saves/')]),1)
        self.assertEqual(before,snapshot(self.card))

    def test_cps2_aliases_and_identical_rom_copies_keep_all_sources_and_distinct_settings(self):
        from menu_bindings import page, validate

        directory = self.card/'Assets/jtcps2/common'
        for name in ('game.rom','copy.rom'):
            put(directory/name,b'\x07'*32768)
        for name,rom,buttons in (('a','game.rom',0x543210),('b','game.rom',0x543210),
                                 ('c','copy.rom',0x543210),('d','game.rom',0x543201)):
            delivery.write(directory/(name+'.json'),cps_instance(rom,buttons))
        before = snapshot(self.card)
        build_menus.build(self.card,self.root/'aliases',['CPS2'])
        lib = self.root/'aliases/libraries/CPS2'
        manifest = delivery.read(lib/'library-manifest.json')
        validate(lib,manifest,'CPS2','GBAF2')
        self.assertEqual(len(manifest['instances']),4)
        self.assertEqual(len(manifest['source_refs']),2)
        self.assertEqual(len(manifest['runtime_bindings']),2)
        bound = next(r for r in manifest['runtime_bindings'] if r['button_map']==0x543210)
        self.assertEqual(len(bound['instance_paths']),3)
        self.assertEqual(len(bound['rom_paths']),2)
        self.assertEqual(manifest['duplicate_menu_paths'],['Assets/jtcps2/common/b.json','Assets/jtcps2/common/c.json'])
        games = [e for row in manifest['files'] if row['path'].startswith('Assets/')
                 for e in page((lib/row['path']).read_bytes(),'CPS2','GBAF2') if not e['folder']]
        self.assertEqual(len(games),2)
        self.assertEqual({e['cps_settings'][1] for e in games},{0x543210,0x543201})
        self.assertEqual(snapshot(self.card),before)
        bound['instance_paths'].pop()
        with self.assertRaisesRegex(ValueError,'runtime binding inventory'):
            validate(lib,manifest,'CPS2','GBAF2')

    def test_cps2_alias_nvram_conflicts_and_late_source_changes_are_not_lost(self):
        import progress_import

        directory = self.card/'Assets/jtcps2/common'
        put(directory/'game.rom',b'\x07'*32768)
        entries_by_name = {}
        for index,name in enumerate(('first','second')):
            instance = cps_instance('game.rom')
            instance['instance']['data_slots'][1]['filename'] = name+'.sav'
            delivery.write(directory/(name+'.json'),instance)
            put(self.card/f'Saves/jtcps2/common/{name}.sav',bytes([index+1])*128)
            entries_by_name[name] = instance
        before = snapshot(self.card)
        build_menus.build(self.card,self.root/'aliases',['CPS2'])
        lib = self.root/'aliases/libraries/CPS2'
        package = self.root/'package'
        cps_package(package)
        components = [{'id':'CPS2','package':str(package),'library':str(lib)}]
        config = self.root/'inputs/delivery.json'
        delivery.write(config,{'components':components,'save_import':{}})
        with self.assertRaises(progress_import.Conflict):
            delivery.prepare(self.card,config,self.root/'conflict')
        self.assertEqual(snapshot(self.card),before)
        self.assertFalse((self.root/'conflict/delivery-plan.json').exists())
        report,_ = progress_import.collect(self.card,components,self.root,{})
        self.assertEqual(report['conflicts'],1)
        row = report['games'][0]
        self.assertEqual({r['save']['path'] for r in row['candidates']},
                         {'Saves/jtcps2/common/first.sav','Saves/jtcps2/common/second.sav'})
        choice = next(r['id'] for r in row['candidates'] if r['save']['path'].endswith('/second.sav'))
        delivery.write(config,{'components':components,'save_import':{'choices':{row['path']:choice}}})
        stage = self.root/'selected'
        plan = delivery.prepare(self.card,config,stage)
        self.assertTrue({'Assets/jtcps2/common/first.json','Assets/jtcps2/common/second.json'}
                        <= {r['path'] for r in plan['guards']})
        original_json = (directory/'second.json').read_bytes()
        put(directory/'second.json',original_json+b' ')
        with self.assertRaisesRegex(ValueError,'identity changed'):
            delivery.apply(self.card,stage,self.root/'rejected-backup')
        self.assertFalse((self.root/'rejected-backup').exists())
        put(directory/'second.json',original_json)
        old_save = self.card/'Saves/jtcps2/common/second.sav'
        put(old_save,b'\x03'*128)
        with self.assertRaisesRegex(ValueError,'identity changed'):
            delivery.apply(self.card,stage,self.root/'rejected-save-backup')
        self.assertFalse((self.root/'rejected-save-backup').exists())
        put(old_save,b'\x02'*128)
        delivery.apply(self.card,stage,self.root/'backup')
        target = self.card/row['path']
        self.assertEqual(target.read_bytes(),b'\x02'*128)
        put(target,b'new play'.ljust(128,b'\x04'))
        delivery.rollback(self.card,self.root/'backup',execute=True)
        self.assertTrue(target.read_bytes().startswith(b'new play'))
        self.assertFalse((self.card/'Cores/pocketlab.CPS2/core.json').exists())
        self.assertEqual({p:delivery.sha(self.card/p) for p in before},before)

    def test_cps2_jotego_layout_uses_shared_rom_and_original_nvram(self):
        from progress_import import collect

        original = 'Assets/jtcps2/jotego.jtcps2/Arcade.json'
        rom = 'Assets/jtcps2/common/sets/game.rom'
        save = 'Saves/jtcps2/common/sets/progress.sav'
        raw = b'\x07' * 32768
        put(self.card/rom, raw)
        put(self.card/save, b'P' * 128)
        fixture = cps_instance('game.rom')
        fixture['instance']['memory_writes'].pop()  # The stock instance omits the default mapping.
        fixture['instance']['data_path'] = 'sets/'
        fixture['instance']['data_slots'][0]['md5'] = hashlib.md5(raw).hexdigest()
        delivery.write(self.card/original, fixture)
        fixture['instance']['data_slots'][0]['md5'] = '0' * 32
        delivery.write(self.card/'Assets/jtcps2/jotego.jtcps2/Wrong image.json', fixture)
        fixture['instance']['data_slots'][0]['filename'] = 'missing.rom'
        delivery.write(self.card/'Assets/jtcps2/jotego.jtcps2/Missing.json', fixture)
        before = snapshot(self.card)

        out = self.root/'native'
        result = build_menus.build(self.card, out, systems=['CPS2'])
        self.assertEqual(result['systems']['CPS2']['source_files_discovered'], 2)
        manifest = delivery.read(out/'libraries/CPS2/library-manifest.json')
        self.assertEqual([(r['path'], r['rom_path'], r['button_map']) for r in manifest['instances']],
                         [(original, rom, 0x543210)])
        self.assertEqual({r['reason'] for r in manifest['excluded']},
                         {'CPS2 instance ROM is missing', 'CPS2 instance ROM checksum differs'})
        report, payloads = collect(self.card, delivery.read(out/'delivery.json')['components'], out, {})
        self.assertEqual(report['imports'], 1)
        self.assertEqual(list(payloads.values()), [(b'P' * 128, None)])
        self.assertEqual(before, snapshot(self.card))

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

    def test_missing_art_gives_each_filename_a_distinct_card_in_all_formats(self):
        profiles={'GB-GBC':('gb','gb'),'GBA':('gba','gba'),'NES':('nes','nes'),
                  'GG':('gg','gg'),'SMS':('sms','sms'),'SG1000':('sg1000','sg')}
        for _,(platform,suffix) in profiles.items():
            for index,name in enumerate(('陌生旅程甲','陌生旅程乙')):
                if platform=='gba':raw=gba_rom(index)
                elif platform=='nes':raw=b'NES\x1a'+bytes([1])+bytes(11)+bytes(16383)+bytes([index])
                else:raw=bytes(32767)+bytes([index])
                put(self.card/f'Assets/{platform}/common/{name}.{suffix}',raw)
        before=snapshot(self.card);build_menus.build(self.card,self.root/'out')
        for system in profiles:
            games,_=entries(self.root/'out/libraries'/system,artwork=True)
            cards=[art for art,_ in games.values()]
            self.assertEqual(len(cards),2);self.assertNotEqual(cards[0],cards[1])
            self.assertTrue(all(card!=build_library.picture(None) for card in cards))
        self.assertEqual(before,snapshot(self.card))

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

    def test_gb_missing_glyph_warning_survives_text_cover_generation(self):
        rel='Assets/gb/common/Own.gb';put(self.card/rel,bytes(32768))
        aliases=self.root/'names.json';delivery.write(aliases,{rel:'自选\U0010ffff'})
        before=snapshot(self.card);build_menus.build(self.card,self.root/'out',titles=aliases)
        manifest=delivery.read(self.root/'out/libraries/GB-GBC/library-manifest.json')
        self.assertTrue(any('\U0010ffff' in row.get('missing_glyphs',[]) for row in manifest['warnings']))
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
