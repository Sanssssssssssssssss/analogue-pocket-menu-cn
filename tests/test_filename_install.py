# SPDX-License-Identifier: MIT
"""Synthetic build -> install -> refresh -> rollback; no physical acceptance."""
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import build_menus
import build_release
import delivery
import style_library


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def gba_rom(tag=0):
    raw = bytearray(32768)
    raw[0xA0:0xAC] = b'LAB FIXTURE '
    raw[0xAC:0xB0] = b'TEST'
    raw[0xB2] = 0x96
    raw[0xBD] = (-sum(raw[0xA0:0xBD])-0x19) & 255
    raw[-1] = tag
    return raw


class FilenameInstall(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.card, self.inputs = self.root/'card', self.root/'inputs'
        put(self.card/'Analogue_Pocket.json', b'{"product":"Analogue Pocket"}')
        put(self.card/'Saves/gba/common/MinishCap.sav', b'important original progress')
        self.roms = {'GB-GBC': 'Assets/gb/common/我的冒险.gb', 'GBA': 'Assets/gba/common/新旅程.gba',
                     'NES': 'Assets/nes/common/红白机.nes', 'GG': 'Assets/gg/common/星の冒険.gg',
                     'SMS': 'Assets/sms/common/主机游戏.sms', 'SG1000': 'Assets/sg1000/common/早期主机.sg'}
        for name, relative in self.roms.items():
            raw = gba_rom() if name == 'GBA' else b'NES\x1a' + bytes([1]) + bytes(11) + bytes(16384) if name == 'NES' else bytes(32768)
            put(self.card/relative, raw)
        put(self.card/'Assets/gbc/common/彩色冒险.gbc', b'\x01'*32768)
        put(self.card/'Assets/gbc/common/gbc_bios.bin', bytes(2304))
        put(self.card/'Assets/gba/common/gba_bios.bin', bytes(16384))
        package = self.inputs/'packages/GB-GBC'
        shutil.copytree(ROOT/'packaging', package/'core')
        put(package/'core/Cores/pocketlab.CoverFlow/gbc.rbf_r', b'synthetic accepted GB bitstream')
        accepted = delivery.sha(package/'core/Cores/pocketlab.CoverFlow/gbc.rbf_r')
        mocked = patch.object(build_release, 'RBF_SHA', accepted)
        mocked.start()
        self.addCleanup(mocked.stop)
        delivery.write(package/'core/release-manifest.json', {'version': 'fixture', 'bitstream_sha256': accepted,
                       'files': [delivery.snapshot(p, p.relative_to(package/'core').as_posix())
                                 for p in (package/'core').rglob('*') if p.is_file()]})
        for name in ('GBA', 'NES', 'GG', 'SMS', 'SG1000'):
            self.package(name)
        build_menus.build(self.card, self.inputs/'menus')

    def package(self, name):
        short, ns, platform = delivery.PROFILES[name]
        package = self.inputs/'packages'/name
        core = package/f'core/Cores/pocketlab.{short}'
        if name == 'GBA':
            slots = [{'id': 100}, {'id': 4, 'filename': 'gba_bios.bin', 'parameters': '0x1000008',
                      'address': '0x30000000', 'size_exact': 16384}, {'id': 1}, {'id': 10}, {'id': 11}]
        elif name == 'NES':
            slots = [{'id': i} for i in (100, 0, 10, 11)]
        else:
            slot, address = {'GG': (1, 0x10000000), 'SMS': (4, 0x30000000), 'SG1000': (5, 0x60000000)}[name]
            slots = [{'id': 100}, {'id': slot, 'address': hex(address)}, {'id': 2, 'size_maximum': '0x8000'}, {'id': 3}]
        modes = [{'width': 240, 'height': 160, 'aspect_w': 3, 'aspect_h': 2},
                 {'width': 320, 'height': 288, 'aspect_w': 10, 'aspect_h': 9}]
        if name in ('GG', 'SMS', 'SG1000'):
            modes = [{'width': 160, 'height': 144}]*4 + modes[1:] + [{'width': 256, 'height': 240}]
        metadata = dict(author='pocketlab', shortname=short, platform_ids=[ns, platform],
                        description='Synthetic first-install fixture', url='https://example.org', version='fixture', date_release='2026-11-03')
        contents = {'core': {'core': {'magic': 'APF_VER_1', 'metadata': metadata,
                    'framework': {'sleep_supported': False, 'hardware': {'cartridge_adapter': -1}},
                    'cores': [{'filename': platform+'.rbf_r'}]}},
                    'data': {'data': {'magic': 'APF_VER_1', 'data_slots': slots}},
                    'video': {'video': {'magic': 'APF_VER_1', 'scaler_modes': modes}},
                    'variants': {'variants': {'magic': 'APF_VER_1', 'variant_list': []}}}
        for kind in ('audio', 'input', 'interact'):
            contents[kind] = {kind: {'magic': 'APF_VER_1'}}
        for kind, value in contents.items():
            delivery.write(core/(kind+'.json'), value)
        put(core/(platform+'.rbf_r'), b'synthetic '+platform.encode()+b' bitstream')
        delivery.write(package/f'core/Platforms/{ns}.json', {})
        put(package/f'core/Platforms/_images/{ns}.bin', b'synthetic icon')
        delivery.write(package/'build-receipt.json', {'core': 'pocketlab.'+short, 'version': 'fixture',
                       'minimum_slack_ns': 1, 'minimum_reported_slack_ns': 1, 'timing_records': 72,
                       'platform': platform, 'namespace': ns,
                       'menu_format': 'GBAF2' if name == 'GBA' else 'GBAF2/NES' if name == 'NES' else 'GBAF2/Sega'})
        self.rehash_package(name)

    def rehash_package(self, name):
        package = self.inputs/'packages'/name
        receipt = delivery.read(package/'build-receipt.json')
        receipt['files'] = [delivery.snapshot(p, p.relative_to(package/'core').as_posix())
                            for p in (package/'core').rglob('*') if p.is_file()]
        delivery.write(package/'build-receipt.json', receipt)

    def config(self, systems=None, menus='menus'):
        systems = systems or self.roms
        path = self.inputs/(menus+'-delivery.json')
        delivery.write(path, {'components': [{'id': s, 'package': 'packages/'+s,
                        'library': menus+'/libraries/'+s} for s in systems]})
        return path

    def first(self, systems=None):
        staging = self.root/'first'
        result = delivery.prepare(self.card, self.config(systems), staging)
        delivery.apply(self.card, staging, self.root/'first-backup')
        return result

    def test_all_six_filename_outputs_install_and_rollback_keep_original_and_new_progress(self):
        before = snapshot(self.card)
        shutil.copytree(self.inputs/'packages', self.inputs/'menus/packages')
        result = delivery.prepare(self.card, self.inputs/'menus/delivery.json', self.root/'first')
        delivery.apply(self.card, self.root/'first', self.root/'first-backup')
        self.assertTrue(all(c['operation'] == 'first_addition' for c in result['components'].values()))
        self.assertEqual(result['directories'], delivery.save_directories(self.roms))
        for relative in result['directories']:
            self.assertTrue((self.card/relative).is_dir())
        for relative, digest in before.items():
            self.assertEqual(delivery.sha(self.card/relative), digest)
        played = self.card/'Saves/gbalab/common'/('a'*20+'.sav')
        put(played, b'played native progress')
        delivery.rollback(self.card, self.root/'first-backup', execute=True)
        self.assertEqual(played.read_bytes(), b'played native progress')
        self.assertTrue(all((self.card/relative).is_dir() for relative in result['directories']))
        self.assertTrue(all(delivery.sha(self.card/r) == digest for r, digest in before.items()))
        self.assertFalse((self.card/'Cores/pocketlab.GBA/core.json').exists())

    def test_gb_gba_refresh_adds_games_preserves_current_metadata_and_latest_played_progress(self):
        self.first(['GB-GBC', 'GBA'])
        protected = {}
        for system in ('GB-GBC', 'GBA'):
            short, ns, _ = delivery.PROFILES[system]
            core = self.card/('Cores/pocketlab.'+short)
            video = delivery.read(core/'video.json')
            video['video']['defaults'] = {'sharpness': 2}
            delivery.write(core/'video.json', video)
            protected.update({p.relative_to(self.card).as_posix(): p.read_bytes() for p in core.iterdir()})
            tag = delivery.sha(self.card/self.roms[system])[:20]
            put(self.card/f'Saves/{ns}/common/{tag}.sav', b'latest played '+system.encode())
        put(self.card/'Assets/gb/common/新增游戏.gb', b'\x05'*32768)
        put(self.card/'Assets/gba/common/新增游戏.gba', gba_rom(7))
        aliases = self.inputs/'aliases.json'
        delivery.write(aliases, {self.roms['GB-GBC']: '更新后的中文名', self.roms['GBA']: '更新后的 GBA 中文名'})
        build_menus.build(self.card, self.inputs/'menus2', ['GB-GBC', 'GBA'], titles=aliases)
        before = snapshot(self.card)
        plan = delivery.prepare(self.card, self.config(['GB-GBC', 'GBA'], 'menus2'), self.root/'refresh')
        self.assertTrue(all(c['operation'] == 'library_refresh_same_bitstream' for c in plan['components'].values()))
        self.assertFalse(any(c['path'].startswith(('Cores/', 'Platforms/', 'Saves/')) for c in plan['changes']))
        delivery.apply(self.card, self.root/'refresh', self.root/'refresh-backup')
        for relative, data in protected.items():
            self.assertEqual((self.card/relative).read_bytes(), data)
        added = self.card/'Saves/gbalab/common'/('b'*20+'.sav')
        put(added, b'newly played after refresh')
        delivery.rollback(self.card, self.root/'refresh-backup', execute=True)
        self.assertTrue(all(delivery.sha(self.card/r) == digest for r, digest in before.items()))
        self.assertEqual(added.read_bytes(), b'newly played after refresh')

    def test_renamed_roms_refresh_into_new_paths_with_the_same_content_save_ids(self):
        self.first(['GB-GBC', 'GBA'])
        tags = {s: delivery.sha(self.card/self.roms[s])[:20] for s in ('GB-GBC', 'GBA')}
        for system in tags:
            old = self.card/self.roms[system]
            renamed = old.with_name('中文改名'+old.suffix)
            self.assertTrue(renamed.resolve().is_relative_to(self.card))
            old.rename(renamed)
            ns = delivery.PROFILES[system][1]
            put(self.card/f'Saves/{ns}/common/{tags[system]}.sav', b'played before rename')
        build_menus.build(self.card, self.inputs/'renamed', ['GB-GBC', 'GBA'])
        plan = delivery.prepare(self.card, self.config(['GB-GBC', 'GBA'], 'renamed'), self.root/'rename-refresh')
        delivery.apply(self.card, self.root/'rename-refresh', self.root/'rename-backup')
        for system, tag in tags.items():
            self.assertEqual((self.card/f'Saves/{delivery.PROFILES[system][1]}/common/{tag}.sav').read_bytes(), b'played before rename')
        self.assertTrue(all(c['operation'] == 'library_refresh_same_bitstream' for c in plan['components'].values()))

    def test_gba_bios_change_after_preparation_stops_before_backup(self):
        staging = self.root/'bios-check'
        delivery.prepare(self.card, self.config(['GBA']), staging)
        put(self.card/'Assets/gba/common/gba_bios.bin', b'\x11'*16384)
        before = snapshot(self.card)
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            delivery.apply(self.card, staging, self.root/'must-not-exist')
        self.assertEqual(snapshot(self.card), before)
        self.assertFalse((self.root/'must-not-exist').exists())

    def test_unified_cheat_index_is_version_matched_and_refresh_cannot_silently_disable_it(self):
        raw = (self.card/self.roms['GG']).read_bytes()
        index = self.inputs/'cheats.json'
        delivery.write(index, {'format': 'SEGA-CHEATS1', 'profiles': [{
            'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'sha1': hashlib.sha1(raw).hexdigest(), 'crc32': f'{zlib.crc32(raw)&0xffffffff:08x}',
            'source': {'url': 'https://example.org/synthetic-cheats', 'commit': 'a'*40, 'license': 'MIT'},
            'effects': [{'title': '实用测试效果', 'codes': [{'type': 'par', 'address': 0xC100, 'value': 9}]}]}]})
        generated = build_menus.build(self.card, self.inputs/'with-cheats', ['GG'], cheats=index)
        self.assertEqual(generated['systems']['GG']['cheat_matched_versions'], 1)
        delivery.prepare(self.card, self.config(['GG'], 'with-cheats'), self.root/'cheat-first')
        delivery.apply(self.card, self.root/'cheat-first', self.root/'cheat-backup')
        code = next((self.card/'Assets/ggclab/cheat').glob('*.cht'))
        original = code.read_bytes()
        self.assertIn(b'_enable = true', original)
        before = snapshot(self.card)
        with self.assertRaisesRegex(ValueError, 'matched cheats would be disabled'):
            delivery.prepare(self.card, self.config(['GG']), self.root/'missing-index')
        self.assertEqual(snapshot(self.card), before)
        build_menus.build(self.card, self.inputs/'with-cheats2', ['GG'], cheats=index)
        delivery.prepare(self.card, self.config(['GG'], 'with-cheats2'), self.root/'cheat-refresh')
        delivery.apply(self.card, self.root/'cheat-refresh', self.root/'cheat-refresh-backup')
        self.assertEqual(code.read_bytes(), original)

    def test_legacy_gb_save_or_changed_native_content_does_not_silently_reset_progress(self):
        self.first(['GB-GBC', 'GBA', 'NES'])
        manifest = delivery.read(self.inputs/'menus/libraries/GB-GBC/library-manifest.json')
        for row in manifest['files']:
            if not row['path'].endswith('.bin') or 'bios' in row['path']:
                continue
            path = self.card/row['path']
            decoded = style_library.decode(path.read_bytes())
            game = next((e for e in decoded['entries'] if not e['record'][40] & 128), None)
            if game:
                game['paths'][1:] = ['/Saves/gbclab/common/legacy.sav', '/Saves/gbclab/common/legacy.sus']
                path.write_bytes(style_library.encode(decoded))
                break
        put(self.card/'Saves/gbclab/common/legacy.sav', b'played legacy GB progress')
        before = snapshot(self.card)
        with self.assertRaisesRegex(ValueError, 'legacy save IDs'):
            delivery.prepare(self.card, self.config(['GB-GBC']), self.root/'legacy-gb')
        self.assertEqual(snapshot(self.card), before)
        for system in ('GBA', 'NES'):
            raw = gba_rom(9) if system == 'GBA' else bytearray((self.card/self.roms[system]).read_bytes())
            raw[-1] = 9
            put(self.card/self.roms[system], raw)
            menus = 'changed-'+system
            build_menus.build(self.card, self.inputs/menus, [system])
            before = snapshot(self.card)
            with self.assertRaisesRegex(ValueError, 'content or save identity changed'):
                delivery.prepare(self.card, self.config([system], menus), self.root/menus)
            self.assertEqual(snapshot(self.card), before)

    def test_original_f1_first_install_still_passes_complete_library_checks(self):
        package = self.inputs/'packages/GBA'
        receipt = delivery.read(package/'build-receipt.json')
        receipt['menu_format'] = 'GBAF1'
        delivery.write(package/'build-receipt.json', receipt)
        installer = delivery.module('experiments/gba_menu/install.py')
        before = snapshot(self.card)
        result = installer.plan(self.card, package, self.inputs/'menus/intermediate/GBAF1')
        self.assertEqual(result['operation'], 'first_addition')
        self.assertEqual(result['roms'], 1)
        self.assertEqual(snapshot(self.card), before)

    def test_unreachable_gb_page_and_missing_gba_game_content_are_rejected(self):
        library = self.inputs/'menus/libraries/GB-GBC'
        manifest = delivery.read(library/'library-manifest.json')
        relative = 'Assets/gbclab/common/libs/'+'f'*16+'.bin'
        put(library/relative, (library/'Assets/gbclab/common/covers.bin').read_bytes())
        # Give the otherwise-valid duplicate page its own metadata filenames.
        raw = bytearray((library/relative).read_bytes())
        tail = [f'/Saves/gbclab/common/meta/{"f"*16}.{ext}' for ext in ('log', 'cfg')]
        raw[-512:] = b''.join(v.encode().ljust(256, b'\0') for v in tail)
        (library/relative).write_bytes(raw)
        manifest['files'].append(delivery.snapshot(library/relative, relative))
        delivery.write(library/'library-manifest.json', manifest)
        before = snapshot(self.card)
        with self.assertRaisesRegex(ValueError, 'Unreachable'):
            delivery.prepare(self.card, self.config(['GB-GBC']), self.root/'orphan')
        self.assertEqual(snapshot(self.card), before)
        library = self.inputs/'menus/libraries/GBA'
        manifest = delivery.read(library/'library-manifest.json')
        for row in manifest['files']:
            path = library/row['path']
            raw = bytearray(path.read_bytes())
            for i in range(int.from_bytes(raw[8:12], 'little')):
                at = 64+i*1024
                if not raw[at+4]:
                    raw[at+4] = 1
                    raw[at+32:at+288] = b'/Assets/gbalab/common/menu.bin'.ljust(256, b'\0')
            path.write_bytes(raw)
            row['sha256'] = delivery.sha(path)
        delivery.write(library/'library-manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'missing game content'):
            delivery.prepare(self.card, self.config(['GBA']), self.root/'missing-game')
        self.assertEqual(snapshot(self.card), before)

    def test_first_gba_refuses_an_original_save_link_even_with_a_rehashed_manifest(self):
        library = self.inputs/'menus/libraries/GBA'
        manifest = delivery.read(library/'library-manifest.json')
        for row in manifest['files']:
            p = library/row['path']
            raw = bytearray(p.read_bytes())
            count = int.from_bytes(raw[8:12], 'little')
            for i in range(count):
                at = 64+i*1024
                if raw[at+4]:
                    continue
                raw[at+288:at+544] = b'/Saves/gba/common/MinishCap.sav'.ljust(256, b'\0')
            p.write_bytes(raw)
            row['sha256'] = delivery.sha(p)
        delivery.write(library/'library-manifest.json', manifest)
        before = snapshot(self.card)
        with self.assertRaisesRegex(ValueError, 'namespace|save identity'):
            delivery.prepare(self.card, self.config(['GBA']), self.root/'bad-save-link')
        self.assertEqual(snapshot(self.card), before)
        self.assertFalse((self.root/'bad-save-link/delivery-plan.json').exists())

    def test_bad_gba_bios_platform_or_scaler_and_partial_gb_entry_are_refused(self):
        core = self.inputs/'packages/GBA/core/Cores/pocketlab.GBA'
        for file in ('data.json', 'video.json'):
            original = (core/file).read_bytes()
            value = delivery.read(core/file)
            if file == 'data.json':
                value['data']['data_slots'][1]['parameters'] = '0x8'
            else:
                value['video']['scaler_modes'].pop()
            delivery.write(core/file, value)
            self.rehash_package('GBA')
            before = snapshot(self.card)
            with self.assertRaisesRegex(ValueError, 'BIOS slot|scaler slot'):
                delivery.prepare(self.card, self.config(['GBA']), self.root/('bad-'+file))
            self.assertEqual(snapshot(self.card), before)
            (core/file).write_bytes(original)
            self.rehash_package('GBA')
        put(self.card/'Cores/pocketlab.CoverFlow/gbc.rbf_r', b'synthetic accepted GB bitstream')
        before = snapshot(self.card)
        with self.assertRaisesRegex(ValueError, 'existing destination'):
            delivery.prepare(self.card, self.config(['GB-GBC']), self.root/'partial-gb')
        self.assertEqual(snapshot(self.card), before)


if __name__ == '__main__':
    unittest.main()
