# SPDX-License-Identifier: MIT
"""Synthetic installer transactions; these tests are not FPGA acceptance."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import additional_menus
import build_menus
import delivery
import menu_bindings
import progress_import


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def package(root, system):
    """A deliberately synthetic reviewed fixture, never a distributable core."""
    profile = additional_menus.PROFILES[system]
    prefix = f'Cores/pocketlab.{profile["short"]}'
    dest = root/'core'/prefix
    documents = {name: {name: {'magic': 'APF_VER_1'}} for name in ('audio','data','input','interact','variants','video')}
    documents['core'] = {'core': {'magic': 'APF_VER_1', 'metadata': {
        'author': 'pocketlab', 'shortname': profile['short'],
        'platform_ids': [profile['namespace'],profile['platform']]+profile.get('extra_platforms', []),
        'version': 'synthetic-test', 'date_release': '2026-11-15', 'description': 'Installer test fixture', 'url': 'https://example.com'},
        'framework': {'sleep_supported': False}, 'cores': [dict(name='default',id=0,filename=profile['binary']+'.rbf_r')]}}
    documents['data']['data']['data_slots'] = []
    documents['variants']['variants']['variant_list'] = []
    documents['video']['video']['scaler_modes'] = [{'width':320,'height':288}]
    for name, value in documents.items():
        delivery.write(dest/(name+'.json'), value)
    put(dest/(profile['binary']+'.rbf_r'), b'SYNTHETIC INSTALLER FIXTURE - NOT FPGA DATA')
    if system == 'NEOGEO':
        put(dest/'licenses/FX68K-NOTICE.md', b'Synthetic Neo Geo license notice')
    delivery.write(root/'core/Platforms'/f'{profile["namespace"]}.json', {'platform': {'name':system,'category':'CN Menu'}})
    source = root/'sources/fixture.txt'
    put(source, b'Synthetic fixture provenance')
    digest = delivery.sha(dest/(profile['binary']+'.rbf_r'))
    receipt = dict(core='pocketlab.'+profile['short'], namespace=profile['namespace'], menu_format='GBAF2/'+profile['platform'],
        bitstream_sha256=digest, version='synthetic-test', timing_records=40, minimum_slack_ns=0.1,
        source_inputs={'fixture.txt':delivery.sha(source)}, files=[delivery.snapshot(p,p.relative_to(root/'core').as_posix()) for p in (root/'core').rglob('*') if p.is_file()])
    delivery.write(root/'build-receipt.json', receipt)
    return digest, {'receipt_sha256': delivery.sha(root/'build-receipt.json')}


class AdditionalTransactions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.card = self.base/'card'
        put(self.card/'Analogue_Pocket.json', b'{"product":"Analogue Pocket"}')
        put(self.card/'Saves/gba/common/MinishCap.sav', b'precious existing progress')

    def test_atari_install_refresh_restore_preserve_shared_saves_and_settings(self):
        rom = self.card/'Assets/2600/common/动作/测试.a26'
        put(rom, bytes(range(256))*16)
        save = self.card/'Saves/2600/common/savekey.sav'
        put(save, bytes(range(256))*128)
        package_root = self.base/'inputs/package'
        digest, record = package(package_root, 'ATARI2600')
        registry = self.base/'registry.json'
        delivery.write(registry, {'ATARI2600':{digest:record}})
        library = self.base/'library'
        additional_menus.library(self.card,library,'ATARI2600')
        config = self.base/'inputs/delivery.json'
        delivery.write(config, {'components':[{'id':'ATARI2600','package':str(package_root),'library':str(library)}]})
        with patch.object(additional_menus,'REGISTRY',registry):
            stage = self.base/'stage'
            delivery.prepare(self.card,config,stage)
            result = delivery.apply(self.card,stage,self.base/'backup')
            self.assertEqual(result['status'],'installed_sha256_verified_hardware_pending')
            self.assertEqual(save.read_bytes(),bytes(range(256))*128)
            self.assertEqual((self.base/'backup/progress/Saves/2600/common/savekey.sav').read_bytes(),save.read_bytes())
            setting = self.card/'Cores/pocketlab.Atari2600/video.json'
            original = setting.read_bytes()
            value = delivery.read(setting)
            value['video']['user_setting'] = 'retained'
            delivery.write(setting,value)
            stage2 = self.base/'stage2'
            delivery.prepare(self.card,config,stage2)
            delivery.apply(self.card,stage2,self.base/'backup2')
            self.assertEqual(delivery.read(setting)['video']['user_setting'],'retained')
            save.write_bytes(b'new played data'.ljust(32768,b'\0'))
            # Restore the first receipt's expected core metadata so the test
            # exercises progress retention, not a metadata-conflict bypass.
            setting.write_bytes(original)
            delivery.rollback(self.card,self.base/'backup',execute=True)
            self.assertTrue(save.read_bytes().startswith(b'new played data'))
            self.assertEqual(rom.read_bytes(),bytes(range(256))*16)
            self.assertFalse((self.card/'Cores/pocketlab.Atari2600/core.json').exists())

    def test_changed_corresponding_source_and_unregistered_bitstream_are_refused(self):
        package_root = self.base/'package'
        digest, record = package(package_root,'ATARI7800')
        registry = self.base/'registry.json'
        delivery.write(registry,{})
        with patch.object(additional_menus,'REGISTRY',registry):
            with self.assertRaisesRegex(ValueError,'reviewed build receipt'):
                additional_menus.registered(package_root,'ATARI7800')
            delivery.write(registry,{'ATARI7800':{digest:record}})
            additional_menus.registered(package_root,'ATARI7800')
            (package_root/'sources/fixture.txt').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'corresponding source'):
                additional_menus.registered(package_root,'ATARI7800')

    def test_mini_install_refresh_restore_retains_native_and_dedicated_eeprom(self):
        roms = [bytes(range(256))*64, bytes(reversed(range(256)))*128]
        for name, raw in zip(('分类/自备一.min', '自备二.min'), roms):
            put(self.card/'Assets/poke_mini/common'/name, raw)
        native = self.card/'Saves/poke_mini/agg23.PokemonMini/自备一.sav'
        put(native, b'native progress'.ljust(8192,b'\x55'))
        saves = [self.card/f'Saves/pmclab/common/{hashlib.sha256(raw).hexdigest()[:20]}.sav' for raw in roms]
        put(saves[0], b'existing dedicated progress'.ljust(8192,b'\x66'))
        canaries = {p:p.read_bytes() for p in (native,saves[0],self.card/'Saves/gba/common/MinishCap.sav')}
        package_root = self.base/'inputs/package'
        digest, record = package(package_root,'POKEMINI')
        registry = self.base/'registry.json'
        delivery.write(registry,{'POKEMINI':{digest:record}})
        library = self.base/'中文库'
        manifest = additional_menus.library(self.card,library,'POKEMINI')
        self.assertEqual(manifest['game_refs'],2)
        self.assertEqual(manifest['required_bios'],{})
        self.assertEqual(manifest['bios_builtin'],'freebios.hex')
        menu_bindings.validate(library,manifest,'POKEMINI','GBAF2')
        self.assertFalse((library/saves[0].relative_to(self.card)).exists())
        self.assertEqual((library/saves[1].relative_to(self.card)).read_bytes(),b'\xff'*8192)
        config = self.base/'inputs/delivery.json'
        delivery.write(config,{'components':[{'id':'POKEMINI','package':str(package_root),'library':str(library)}]})
        with patch.object(additional_menus,'REGISTRY',registry):
            stage = self.base/'stage'
            plan = delivery.prepare(self.card,config,stage)
            self.assertEqual([r['path'] for r in plan['changes'] if r['path'].startswith('Saves/')],
                             [saves[1].relative_to(self.card).as_posix()])
            result = delivery.apply(self.card,stage,self.base/'backup')
            self.assertEqual(result['status'],'installed_sha256_verified_hardware_pending')
            self.assertTrue((self.card/'Assets/pmclab/common/menu.bin').is_file())
            setting = self.card/'Cores/pocketlab.PokemonMini/video.json'
            original = setting.read_bytes()
            value = delivery.read(setting)
            value['video']['user_setting'] = 'retained'
            delivery.write(setting,value)
            saves[1].write_bytes(b'played after install'.ljust(8192,b'\x77'))
            rom3 = b'new synthetic Mini game'.ljust(12288,b'\x33')
            put(self.card/'Assets/poke_mini/common/新增三.min',rom3)
            library2 = self.base/'刷新库'
            additional_menus.library(self.card,library2,'POKEMINI')
            delivery.write(config,{'components':[{'id':'POKEMINI','package':str(package_root),'library':str(library2)}]})
            plan2 = delivery.prepare(self.card,config,self.base/'stage2')
            self.assertFalse(any(r['path'].startswith('Cores/') for r in plan2['changes']))
            delivery.apply(self.card,self.base/'stage2',self.base/'backup2')
            self.assertEqual(delivery.read(setting)['video']['user_setting'],'retained')
            self.assertTrue(saves[1].read_bytes().startswith(b'played after install'))
            save3 = self.card/f'Saves/pmclab/common/{hashlib.sha256(rom3).hexdigest()[:20]}.sav'
            save3.write_bytes(b'played after refresh'.ljust(8192,b'\x88'))
            delivery.rollback(self.card,self.base/'backup2',execute=True)
            self.assertTrue(save3.read_bytes().startswith(b'played after refresh'))
            # Restore the first receipt's metadata before testing its rollback.
            setting.write_bytes(original)
            delivery.rollback(self.card,self.base/'backup',execute=True)
            self.assertFalse((self.card/'Cores/pocketlab.PokemonMini/core.json').exists())
            self.assertTrue(saves[1].read_bytes().startswith(b'played after install'))
            self.assertTrue(save3.read_bytes().startswith(b'played after refresh'))
            for path, raw in canaries.items():
                self.assertEqual(path.read_bytes(),raw)

    def test_compact_native_formats_reject_injected_unused_paths(self):
        put(self.card/'Assets/supervision/common/动作/自己的游戏.sv', bytes(16384))
        payload = bytes.fromhex('0400000000c0ffcf')
        hex_bytes = b':' + (payload+bytes([-sum(payload)&255])).hex().upper().encode() + b'\n:00000001FF\n'
        put(self.card/'Assets/arduboy/common/冒险/自己的游戏.hex', hex_bytes)
        for system in ('SUPERVISION','ARDUBOY'):
            with self.subTest(system=system):
                library = self.base/system
                manifest = additional_menus.library(self.card,library,system)
                menu_bindings.validate(library,manifest,system,'GBAF2')
                self.assertEqual(manifest['game_refs'],1)
                self.assertTrue(all(r['path'].startswith('Assets/') for r in manifest['source_refs']))
                if system == 'ARDUBOY':
                    self.assertEqual(manifest['source_refs'][0]['save_bytes'],1024)
                namespace = additional_menus.PROFILES[system]['namespace']
                root = library/f'Assets/{namespace}/common/menu.bin'
                raw = bytearray(root.read_bytes())
                # The third path has no meaning in these native controllers.
                # Reject a file that smuggles a save/RTC binding into that field.
                raw[64+544] = ord('/')
                root.write_bytes(raw)
                with self.assertRaisesRegex(ValueError,'Unused native path'):
                    menu_bindings.validate(library,manifest,system,'GBAF2')

    def test_unverified_native_save_layout_is_not_guessed_from_its_size(self):
        for system, size in (('WS',8204),('ARDUBOY',1024),('POKEMINI',8192)):
            with self.subTest(system=system):
                with self.assertRaisesRegex(ValueError,'verified converter'):
                    progress_import.convert(bytes(size),{'system':system,'size':size},'pocket-native')

    def test_discovery_does_not_list_firmware_as_games(self):
        put(self.card/'Assets/7800/common/hsc.a78',bytes(4096))
        put(self.card/'Assets/7800/common/7800bios.bin',bytes(4096))
        put(self.card/'Assets/7800/common/动作/游戏.a78',bytes(4224))
        found=build_menus.discover(self.card)
        self.assertEqual(found['ATARI7800'],['Assets/7800/common/动作/游戏.a78'])


if __name__=='__main__':unittest.main()
