# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import build_library
import build_release
import delivery


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


class Delivery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.card, self.inputs = self.root/'card', self.root/'inputs'
        self.staging, self.backup = self.root/'staging', self.root/'backup'
        put(self.card/'Analogue_Pocket.json', b'{"product":"Analogue Pocket"}')
        self.progress = self.card/'Saves/gba/common/MinishCap.sav'
        put(self.progress, b'important old progress')
        self.rom = 'Assets/gba/common/Synthetic.gba'
        put(self.card/self.rom, b'synthetic game bytes')
        self.old = 'Cores/pocketlab.GBA/core.json'
        put(self.card/self.old, b'old metadata')
        self.inputs.mkdir()

    def parts(self):
        result = []
        for name, files in (
            ('GBA', {self.old: b'new metadata', 'Assets/gbalab/common/menu.bin': b'new page'}),
            ('GG', {'Cores/pocketlab.GG/core.json': b'new native entry',
                    'Saves/ggclab/common/' + 'a'*20 + '.sav': b'isolated seed'})):
            source = self.inputs/name
            changes = []
            for rel, raw in files.items():
                put(source/rel, raw)
                changes.append({**delivery.snapshot(source/rel, rel), 'source': str(source),
                                'previous_sha256': delivery.digest(self.card/rel)})
            result.append((name, {'identity': delivery.identity(self.card), 'changes': changes,
                                 'source_refs': [delivery.snapshot(self.card/self.rom, self.rom)] if name == 'GBA' else []}))
        return result

    def stage(self):
        self.staging.mkdir()
        return delivery.seal(self.card, self.staging, self.parts())

    def test_batch_install_and_rollback_preserve_both_existing_and_new_progress(self):
        before = snapshot(self.card)
        self.stage()
        result = delivery.apply(self.card, self.staging, self.backup)
        self.assertEqual(result['status'], 'installed_sha256_verified_hardware_pending')
        self.assertEqual((self.backup/'previous'/self.old).read_bytes(), before[self.old])
        self.assertEqual((self.backup/'progress'/self.progress.relative_to(self.card)).read_bytes(), b'important old progress')
        self.progress.write_bytes(b'new GBA gameplay')
        seed = next((self.card/'Saves/ggclab/common').glob('*.sav'))
        seed.write_bytes(b'new native gameplay')
        preview = delivery.rollback(self.card, self.backup)
        self.assertFalse(preview['applied'])
        self.assertEqual((self.card/self.old).read_bytes(), b'new metadata')
        delivery.rollback(self.card, self.backup, execute=True)
        self.assertEqual((self.card/self.old).read_bytes(), b'old metadata')
        self.assertEqual(self.progress.read_bytes(), b'new GBA gameplay')
        self.assertEqual(seed.read_bytes(), b'new native gameplay')
        self.assertFalse((self.card/'Cores/pocketlab.GG/core.json').exists())
        self.assertEqual((self.card/self.rom).read_bytes(), before[self.rom])

    def test_source_rom_payload_marker_or_destination_change_aborts_before_backup(self):
        self.stage()
        for path in (self.card/self.rom, self.card/'Analogue_Pocket.json', self.card/self.old,
                     self.staging/'payload'/self.old):
            with self.subTest(path=path.name):
                old = path.read_bytes()
                path.write_bytes(old + b'changed')
                before = snapshot(self.card)
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    delivery.apply(self.card, self.staging, self.backup)
                self.assertEqual(snapshot(self.card), before)
                self.assertFalse(self.backup.exists())
                path.write_bytes(old)

    def test_failure_after_atomic_publish_restores_menu_pair(self):
        self.stage()
        real_publish = delivery.publish
        calls = []
        def interrupted(source, target, expected):
            real_publish(source, target, expected)
            calls.append(target)
            if len(calls) == 2:
                raise OSError('Synthetic lost connection after replace')
        with patch.object(delivery, 'publish', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'lost connection'):
                delivery.apply(self.card, self.staging, self.backup)
        self.assertEqual((self.card/self.old).read_bytes(), b'old metadata')
        self.assertFalse((self.card/'Assets/gbalab/common/menu.bin').exists())
        self.assertFalse((self.card/'Cores/pocketlab.GG/core.json').exists())
        self.assertEqual(self.progress.read_bytes(), b'important old progress')
        self.assertEqual(delivery.read(self.backup/'delivery-receipt.json')['status'],
                         'interrupted_menu_files_restored_saves_retained')

    def test_changed_rollback_target_aborts_whole_preview_before_any_restoration(self):
        self.stage()
        delivery.apply(self.card, self.staging, self.backup)
        (self.card/self.old).write_bytes(b'manual edit after installation')
        before = snapshot(self.card)
        with self.assertRaisesRegex(ValueError, 'Changed file'):
            delivery.rollback(self.card, self.backup, execute=True)
        self.assertEqual(snapshot(self.card), before)

    def test_corrupt_backup_aborts_rollback(self):
        self.stage()
        delivery.apply(self.card, self.staging, self.backup)
        (self.backup/'previous'/self.old).write_bytes(b'broken backup')
        before = snapshot(self.card)
        with self.assertRaisesRegex(ValueError, 'backup identity'):
            delivery.rollback(self.card, self.backup, execute=True)
        self.assertEqual(snapshot(self.card), before)

    def test_later_component_failure_keeps_card_untouched_and_no_delivery_plan(self):
        config = self.inputs/'delivery.json'
        delivery.write(config, {'components': [{'id': 'GBA'}, {'id': 'GG'}]})
        parts = dict(self.parts())
        def planner(card, component, base, out):
            if component['id'] == 'GG':
                raise ValueError('Later component failed preflight')
            return parts[component['id']]
        before = snapshot(self.card)
        with patch.object(delivery, 'component_plan', side_effect=planner):
            with self.assertRaisesRegex(ValueError, 'Later component'):
                delivery.prepare(self.card, config, self.staging)
        self.assertEqual(snapshot(self.card), before)
        self.assertFalse((self.staging/'delivery-plan.json').exists())

    def test_plan_cannot_write_firmware_roms_settings_or_existing_saves(self):
        for rel in ('pocket_firmware.bin', 'Assets/gba/common/Synthetic.gba',
                    'Settings/pocketlab.GBA/settings.json', 'Saves/gba/common/MinishCap.sav',
                    'Cores/pocketlab.GBA/../../pocket_firmware.bin', 'Platforms/../pocket_firmware.bin'):
            with self.subTest(path=rel), self.assertRaises(ValueError):
                delivery.allowed(self.card, rel, 'GBA')
        self.staging.mkdir()
        parts = self.parts()
        row = parts[1][1]['changes'][-1]
        put(self.card/row['path'], b'already played native progress')
        row['previous_sha256'] = delivery.sha(self.card/row['path'])
        with self.assertRaisesRegex(ValueError, 'Existing progress'):
            delivery.seal(self.card, self.staging, parts)

    def test_unchanged_input_guard_is_checked_again_before_apply(self):
        self.staging.mkdir()
        parts = self.parts()
        rel = 'Cores/pocketlab.GBA/data.json'
        put(self.card/rel, b'accepted slot identities')
        parts[0][1]['guards'] = [delivery.snapshot(self.card/rel, rel)]
        delivery.seal(self.card, self.staging, parts)
        (self.card/rel).write_bytes(b'changed slot identities')
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            delivery.apply(self.card, self.staging, self.backup)
        self.assertFalse(self.backup.exists())

    def test_real_gb_preparation_retains_current_icons_metadata_defaults_and_rom_bindings(self):
        package = self.inputs/'GB-GBC'
        shutil.copytree(ROOT/'packaging', package/'core')
        put(package/'core/Cores/pocketlab.CoverFlow/gbc.rbf_r', b'synthetic accepted core')
        shutil.copytree(package/'core', self.card, dirs_exist_ok=True)
        video_path = self.card/'Cores/pocketlab.CoverFlow/video.json'
        video = delivery.read(video_path)
        video['video']['defaults'] = {'sharpness': 1}
        video['video']['display_modes'] = [{'id': '0x10'}]
        delivery.write(video_path, video)
        put(self.card/'Platforms/_images/gbclab.bin', b'current personal machine icon')
        rom = self.card/'Assets/gb/common/Synthetic.gb'
        put(rom, bytes(32768))
        bios = self.inputs/'bios.bin'
        put(bios, bytes(2304))
        library = self.inputs/'gb-library'
        build_library.build(self.card, library, bios=bios)
        shutil.copytree(library/'Assets', self.card/'Assets', dirs_exist_ok=True)
        files = [delivery.snapshot(p, p.relative_to(package/'core').as_posix())
                 for p in (package/'core').rglob('*') if p.is_file()]
        accepted = delivery.sha(self.card/'Cores/pocketlab.CoverFlow/gbc.rbf_r')
        delivery.write(package/'core/release-manifest.json', {'files': files, 'version': 'test-display', 'bitstream_sha256': accepted})
        config = self.inputs/'delivery.json'
        delivery.write(config, {'components': [{'id': 'GB-GBC', 'package': 'GB-GBC'}]})
        before = snapshot(self.card)
        with patch.object(build_release, 'RBF_SHA', accepted):
            result = delivery.prepare(self.card, config, self.staging)
        self.assertEqual(snapshot(self.card), before)
        self.assertTrue(any(r['path'] == rom.relative_to(self.card).as_posix() for r in result['source_refs']))
        self.assertFalse(any(c['path'].startswith('Platforms/') for c in result['changes']))
        delivery.apply(self.card, self.staging, self.backup)
        new_video = delivery.read(video_path)['video']
        self.assertEqual(new_video['defaults'], video['video']['defaults'])
        self.assertEqual(new_video['scaler_modes'], video['video']['scaler_modes'])
        self.assertEqual(new_video['display_modes'][0], {'id': '0x10'})
        delivery.rollback(self.card, self.backup, execute=True)
        self.assertEqual(snapshot(self.card), before)

    def test_real_native_component_adapters_prepare_one_batch(self):
        # Synthetic headers/bitstreams exercise actual builders and planners only.
        # They never demonstrate hardware compatibility.
        raw = bytearray(32768)
        raw[0xA0:0xAC] = b'LAB FIXTURE '
        raw[0xAC:0xB0] = b'TEST'
        raw[0xB2] = 0x96
        raw[0xBD] = (-sum(raw[0xA0:0xBD])-0x19) & 255
        put(self.card/self.rom, raw)
        put(self.card/'Assets/nes/common/Test.nes', b'NES\x1a' + bytes([1]) + bytes(11) + bytes(16384))
        for platform, suffix in (('gg', 'gg'), ('sms', 'sms'), ('sg1000', 'sg')):
            put(self.card/f'Assets/{platform}/common/Test.{suffix}', b'\x11'*32768)
        with delivery.imports():
            f1 = delivery.module('experiments/gba_menu/library.py')
            f2 = delivery.module('experiments/gba_coverflow/library.py')
            f1.build(self.card, self.inputs/'gba-f1')
            shutil.copytree(self.inputs/'gba-f1/Assets', self.card/'Assets', dirs_exist_ok=True)
            f2.upgrade(self.inputs/'gba-f1', self.inputs/'gba-f2')
        components = []
        for name in ('GBA', 'NES', 'GG', 'SMS', 'SG1000'):
            short, ns, platform = delivery.PROFILES[name]
            package = self.inputs/name
            core = package/f'core/Cores/pocketlab.{short}'
            metadata = dict(author='pocketlab', shortname=short, platform_ids=[ns, platform],
                            description='Synthetic delivery fixture', url='https://example.org',
                            version='test', date_release='2026-11-02')
            slots = [{'id': v} for v in ([100,4,1,10,11] if name == 'GBA' else [100,0,10,11])]
            video = {'magic': 'APF_VER_1', 'scaler_modes': [
                {'width':240, 'height':160, 'aspect_w':3, 'aspect_h':2, 'rotation':0, 'mirror':0}],
                     'display_modes': [{'id':'0x10'}], 'defaults': {'sharpness': 1}}
            if name in ('GG', 'SMS', 'SG1000'):
                slot, address = {'GG': (1,0x10000000), 'SMS': (4,0x30000000), 'SG1000': (5,0x60000000)}[name]
                slots = [{'id':100}, {'id':slot, 'address':hex(address)}, {'id':2, 'size_maximum':'0x8000'}, {'id':3}]
                video['scaler_modes'] = [{}]*4 + [{'width':320, 'height':288}, {'width':256, 'height':240}]
            contents = {'core': {'core': {'metadata': metadata, 'framework': {'sleep_supported': False,
                        'hardware': {'cartridge_adapter': -1}}, 'cores': [{'filename':platform+'.rbf_r'}]}},
                        'data': {'data': {'data_slots': slots}}, 'video': {'video':video},
                        'audio': {}, 'input': {}, 'interact': {}}
            for key, value in contents.items():
                delivery.write(core/(key+'.json'), value)
            put(core/(platform+'.rbf_r'), b'synthetic core fixture')
            put(package/f'core/Platforms/_images/{ns}.bin', b'synthetic icon')
            delivery.write(package/f'core/Platforms/{ns}.json', {})
            receipt = {'core':'pocketlab.'+short, 'version':'test', 'minimum_slack_ns':1,
                       'minimum_reported_slack_ns':1, 'timing_records':72,
                       'menu_format':'GBAF2' if name == 'GBA' else 'GBAF2/NES' if name == 'NES' else 'GBAF2/Sega',
                       'platform':platform, 'namespace':ns,
                       'files':[delivery.snapshot(p, p.relative_to(package/'core').as_posix())
                                for p in (package/'core').rglob('*') if p.is_file()]}
            delivery.write(package/'build-receipt.json', receipt)
            component = {'id':name, 'package':name}
            if name == 'GBA':
                shutil.copytree(package/'core', self.card, dirs_exist_ok=True)
                component['library'] = 'gba-f2'
            components.append(component)
        config = self.inputs/'delivery.json'
        delivery.write(config, {'components':components})
        before = snapshot(self.card)
        result = delivery.prepare(self.card, config, self.staging)
        self.assertEqual(snapshot(self.card), before)
        self.assertEqual(set(result['components']), {'GBA','NES','GG','SMS','SG1000'})
        delivery.apply(self.card, self.staging, self.backup)
        gba_video = delivery.read(self.card/'Cores/pocketlab.GBA/video.json')['video']
        self.assertEqual(gba_video['defaults'], {'sharpness':1})
        self.assertEqual(len(gba_video['scaler_modes']), 2)
        delivery.rollback(self.card, self.backup, execute=True)
        after = snapshot(self.card)
        for rel, value in before.items():
            self.assertEqual(after[rel], value)
        for rel in set(after)-set(before):
            self.assertTrue(rel.startswith('Saves/'))


if __name__ == '__main__':
    unittest.main()
