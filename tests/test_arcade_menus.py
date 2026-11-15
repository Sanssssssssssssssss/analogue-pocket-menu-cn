# SPDX-License-Identifier: MIT
"""Arcade instance/save binding tests. No FPGA or real game data is used."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import additional_menus
import delivery
import install
import library_catalog
import progress_import
from test_additional_menus import package, put


class ArcadeTransactions(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.card = self.root/'card'
        put(self.card/'Analogue_Pocket.json', b'{"product":"Analogue Pocket"}')

    def inputs(self, system):
        package_root = self.root/(system+'-package')
        bitstream, record = package(package_root, system)
        registry = self.root/(system+'-registry.json')
        delivery.write(registry, {system:{bitstream:record}})
        return package_root, registry

    def test_native_cps_source_save_race_and_instance_changes_are_rejected(self):
        for system, platform in (('CPS1','jtcps1'), ('CPS15','jtcps15')):
            with self.subTest(system=system):
                rom = f'Assets/{platform}/common/demo.rom'
                original = f'Saves/{platform}/common/demo.sav'
                entry = f'Assets/{platform}/jotego.{platform}/演示.json'
                put(self.card/rom, bytes(range(256))*4)
                put(self.card/original, bytes(range(128)))
                delivery.write(self.card/entry, {'instance':{'magic':'APF_VER_1','data_path':'',
                    'data_slots':[{'id':1,'filename':'demo.rom'},{'id':2,'filename':'demo.sav'}],
                    'memory_writes':[{'address':'0xf9000000','data':'0x0'}]}})
                package_root, registry = self.inputs(system)
                lib = self.root/(system+'-library')
                manifest = additional_menus.library(self.card, lib, system)
                seed = next(r for r in manifest['files'] if r['path'].startswith('Saves/'))
                self.assertEqual((lib/seed['path']).read_bytes(), bytes(range(128)))
                with patch.object(additional_menus, 'REGISTRY', registry):
                    prepared = additional_menus.stage(self.card, package_root, lib, system)
                    self.assertIn(original, {r['path'] for r in prepared['guards']})
                    migration, _ = progress_import.collect(self.card,
                        [{'id':system, 'library':str(lib)}], self.root, {'same_card':True})
                    self.assertEqual(migration['native_instance_imports'], 1)
                    self.assertEqual(migration['imports'], 0)
                    put(self.card/original, b'new play'.ljust(128,b'\0'))
                    with self.assertRaisesRegex(ValueError,'seed differs|source progress'):
                        additional_menus.stage(self.card, package_root, lib, system)
                    put(self.card/original, bytes(range(128)))
                    body = delivery.read(self.card/entry)
                    body['instance']['memory_writes'][0]['data']='0x1'
                    delivery.write(self.card/entry, body)
                    with self.assertRaisesRegex(ValueError,'identity changed|instance changed'):
                        additional_menus.stage(self.card, package_root, lib, system)

    def test_neogeo_native_shared_saves_survive_refresh_and_rollback(self):
        for name in ('uni-bios_4_0.rom','000-lo.lo','sfix.sfix'):
            put(self.card/'Assets/ng/common'/name, bytes(131072))
        slots = []
        for slot in (3,4,5,6,7):
            name = f'segment{slot}.bin'
            put(self.card/'Assets/ng/common/demo'/name, bytes([slot])*1024)
            slots.append({'id':slot, 'filename':name})
        entry = 'Assets/ng/Mazamars312.NeoGeo/动作/演示.json'
        delivery.write(self.card/entry, {'instance':{'magic':'APF_VER_1','data_path':'demo','data_slots':slots}})
        original = 'Saves/ng/common/backup.bak'
        memory = 'Saves/ng/Mazamars312.NeoGeo/动作/演示.sav'
        put(self.card/original, bytes(range(256))*256)
        package_root, registry = self.inputs('NEOGEO')
        config = self.root/'inputs/delivery.json'
        lib = self.root/'library'
        manifest = additional_menus.library(self.card, lib, 'NEOGEO')
        self.assertEqual(manifest['game_refs'],1)
        self.assertEqual((lib/memory).read_bytes(), b'\xff'*8192)
        delivery.write(config, {'components':[{'id':'NEOGEO','package':str(package_root),'library':str(lib)}]})
        with patch.object(additional_menus, 'REGISTRY', registry):
            staging = self.root/'stage'
            delivery.prepare(self.card, config, staging)
            delivery.apply(self.card, staging, self.root/'backup')
            self.assertEqual((self.card/original).read_bytes(), bytes(range(256))*256)
            put(self.card/memory, b'played'.ljust(8192,b'\0'))
            next_lib = self.root/'next-library'
            additional_menus.library(self.card, next_lib, 'NEOGEO')
            additional_menus.stage(self.card, package_root, next_lib, 'NEOGEO')
            delivery.rollback(self.card, self.root/'backup', execute=True)
            self.assertTrue((self.card/memory).read_bytes().startswith(b'played'))
            self.assertEqual((self.card/original).read_bytes(), bytes(range(256))*256)

    def test_new_save_publication_cannot_replace_a_late_arriving_save(self):
        source, target = self.root/'seed', self.root/'save.sav'
        put(source, b'initial seed')
        expected = install.sha(source)
        real_sha = install.sha
        def arrival(path):
            if Path(path).name.startswith('.pocket-menu-') and not target.exists():
                target.write_bytes(b'important new progress')
            return real_sha(path)
        with patch.object(install, 'sha', side_effect=arrival):
            with self.assertRaises(FileExistsError):
                install.publish_new(source, target, expected)
        self.assertEqual(target.read_bytes(), b'important new progress')
        self.assertEqual(list(self.root.glob('.pocket-menu-*')), [])
        new = self.root/'second.sav'
        install.publish_new(source, new, expected)
        self.assertEqual(new.read_bytes(), b'initial seed')

    def test_arcade_display_uses_instance_short_name_without_claiming_content_identity(self):
        relative = 'Assets/ng/Mazamars312.NeoGeo/Custom display name.json'
        delivery.write(self.card/relative, {'instance':{'data_path':'demo'}})
        def fetch(url, limit):
            if url.endswith('.csv'):
                return 'MAME Name,EN Name,CN Name\ndemo,Demonstration,演示游戏\n'.encode()
            if '/git/trees/' in url:
                return json.dumps({'sha':'a'*40,'truncated':False,'tree':[]}).encode()
            raise AssertionError(url)
        with patch.object(library_catalog.build_menus, 'discover', return_value={'NEOGEO':[relative]}):
            report = library_catalog.enrich(self.card, self.root/'metadata', self.root/'cache', ['NEOGEO'], fetch=fetch)
        self.assertEqual(report['games'][0]['title'],'演示游戏')
        self.assertEqual(report['games'][0]['match'],'instance_name')
        self.assertFalse(report['games'][0]['content_identity_confirmed'])


if __name__ == '__main__':
    unittest.main()
