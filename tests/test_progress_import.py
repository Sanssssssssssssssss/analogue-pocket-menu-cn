# SPDX-License-Identifier: MIT
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import delivery
import progress_import as saves
import build_library
import build_release


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def rtc(second=0):
    return (1).to_bytes(4, 'little')+((1 << 29)+(1 << 23)+second).to_bytes(6, 'little')+bytes(6)


class ProgressImport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.card = self.root/'card'
        put(self.card/'Analogue_Pocket.json', b'{"product":"Analogue Pocket"}')
        self.rel = 'Assets/gba/common/中文目录/OurGame.gba'
        put(self.card/self.rel, bytes(range(256))*128)
        ref = delivery.snapshot(self.card/self.rel, self.rel)
        ref['save_bytes'] = 65536
        self.target = 'Saves/gbalab/common/'+ref['sha256'][:20]+'.sav'
        self.old = 'Saves/gba/common/中文目录/OurGame.sav'
        self.components = [{'id': 'GBA', 'library': 'library'}]
        self.inputs = self.root/'inputs'
        delivery.write(self.inputs/'library/library-manifest.json', {'roms': [ref]})

    def collect(self, options=None):
        return saves.collect(self.card, self.components, self.inputs, options or {})[0]

    def test_import_is_in_transaction_and_rollback_keeps_new_play(self):
        put(self.card/self.old, b'\x37'*8192)
        put((self.card/self.old).with_suffix('.rtc'), rtc())
        stage = self.root/'stage'
        stage.mkdir()
        parts = [('GBA', {'identity': delivery.identity(self.card), 'changes': [], 'source_refs': []})]
        report = saves.attach(self.card, self.components, self.inputs, stage, parts, {})
        self.assertEqual(report['imports'], 1)
        delivery.seal(self.card, stage, parts)
        delivery.apply(self.card, stage, self.root/'backup')
        self.assertEqual((self.card/self.target).read_bytes(), b'\x37'*8192+b'\xff'*(65536-8192))
        self.assertEqual((self.card/self.target).with_suffix('.rtc').read_bytes(), rtc())
        self.assertEqual((self.root/'backup/progress'/self.old).read_bytes(), b'\x37'*8192)
        (self.card/self.target).write_bytes(b'\x42'*65536)
        delivery.rollback(self.card, self.root/'backup', execute=True)
        self.assertEqual((self.card/self.target).read_bytes(), b'\x42'*65536)
        self.assertEqual((self.card/self.old).read_bytes(), b'\x37'*8192)

    def test_same_name_wrong_rom_is_never_a_donor(self):
        donor = self.root/'donor'
        put(donor/'Analogue_Pocket.json', b'{"product":"Analogue Pocket"}')
        put(donor/self.rel, b'other cartridge')
        put(donor/self.old, b'\x22'*65536)
        report = self.collect({'sources': [{'root': str(donor)}]})
        self.assertEqual(report['imports'], 0)
        self.assertEqual(report['games'][0]['status'], 'no_source')

    def test_renamed_donor_and_source_change_detected_before_write(self):
        donor = self.root/'donor'
        put(donor/'Analogue_Pocket.json', b'{"product":"Analogue Pocket"}')
        put(donor/'Assets/gba/common/renamed.gba', (self.card/self.rel).read_bytes())
        origin = donor/'Saves/gba/common/renamed.sav'
        put(origin, b'\x21'*65536)
        stage = self.root/'stage'
        stage.mkdir()
        parts = [('GBA', {'identity': delivery.identity(self.card), 'changes': []})]
        saves.attach(self.card, self.components, self.inputs, stage, parts, {'sources': [{'root': str(donor)}]})
        delivery.seal(self.card, stage, parts)
        origin.write_bytes(b'\x22'*65536)
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            delivery.apply(self.card, stage, self.root/'backup')
        self.assertFalse((self.card/self.target).exists())
        self.assertFalse((self.root/'backup').exists())

    def test_conflicts_need_selection_and_existing_target_always_wins(self):
        put(self.card/self.old, b'\x01'*65536)
        put(self.card/(self.old.removesuffix('.sav')+'.gba.sav'), b'\x02'*65536)
        report = self.collect()
        self.assertEqual(report['conflicts'], 1)
        chosen = report['games'][0]['candidates'][1]['id']
        self.assertEqual(self.collect({'choices': {self.target: chosen}})['imports'], 1)
        put(self.card/self.target, b'\x49'*65536)
        self.assertEqual(self.collect()['games'][0]['status'], 'keep_existing')

    def test_equal_bodies_preserve_rtc_from_second_candidate(self):
        put(self.card/self.old, b'\x01'*65536)
        other = self.card/(self.old.removesuffix('.sav')+'.gba.sav')
        put(other, b'\x01'*65536)
        put(other.with_suffix('.rtc'), rtc(3))
        stage = self.root/'stage'
        stage.mkdir()
        parts = [('GBA', {'identity': delivery.identity(self.card), 'changes': []})]
        saves.attach(self.card, self.components, self.inputs, stage, parts, {})
        clock = (stage/'imported-progress'/self.target).with_suffix('.rtc')
        self.assertEqual(clock.read_bytes(), rtc(3))

    def test_oversized_or_foreign_rtc_requires_resolution(self):
        put(self.card/self.old, bytes(131072))
        self.assertEqual(self.collect()['conflicts'], 1)
        (self.card/self.old).write_bytes(bytes(65536))
        put((self.card/self.old).with_suffix('.rtc'), bytes(8))
        self.assertEqual(self.collect()['conflicts'], 1)
        self.assertEqual(self.collect({'choices': {self.target: 'skip'}})['games'][0]['status'], 'explicitly_skipped')

    def test_orphan_current_rtc_is_not_silently_paired(self):
        put(self.card/self.old, bytes(65536))
        put((self.card/self.target).with_suffix('.rtc'), bytes(16))
        self.assertEqual(self.collect()['conflicts'], 1)
        self.assertEqual(self.collect({'choices': {self.target: 'skip'}})['games'][0]['status'], 'explicitly_skipped')

    def test_existing_bad_size_stops_without_overwrite(self):
        put(self.card/self.target, b'bad')
        with self.assertRaisesRegex(ValueError, 'unexpected size'):
            self.collect()
        self.assertEqual((self.card/self.target).read_bytes(), b'bad')

    def test_existing_gba_trailer_is_still_rejected(self):
        raw = b'\x49'*65536 + bytes(range(16))
        put(self.card/self.target, raw)
        with self.assertRaisesRegex(ValueError, 'unexpected size'):
            self.collect()
        self.assertEqual((self.card/self.target).read_bytes(), raw)

    def test_existing_bad_rtc_contents_reported_without_blocking_or_replacing_save(self):
        clock = (self.card/self.target).with_suffix('.rtc')
        put(self.card/self.target, b'\x49' * 65536)
        put(clock, b'\x62' * 16)
        put(self.card/self.old, b'\x11' * 65536)

        report = self.collect()
        self.assertEqual(report['games'][0]['status'], 'keep_existing')
        self.assertEqual(report['existing_rtc_warnings'], 1)
        self.assertEqual(report['existing_save_warnings'], 1)
        self.assertEqual(report['imports'], 0)
        self.assertEqual(report['conflicts'], 0)
        self.assertEqual(clock.read_bytes(), b'\x62' * 16)
        self.assertEqual((self.card/self.target).read_bytes(), b'\x49' * 65536)

    def test_changed_rtc_invalidates_a_previous_selection(self):
        put(self.card/self.old, bytes(65536))
        clock = (self.card/self.old).with_suffix('.rtc')
        put(clock, rtc())
        selected = self.collect()['games'][0]['candidates'][0]['id']
        clock.write_bytes(rtc(1))
        with self.assertRaisesRegex(ValueError, 'source changed'):
            self.collect({'choices': {self.target: selected}})

    def test_rtc_with_wrong_calendar_or_reserved_bytes_is_rejected(self):
        saves.validate_gba_rtc(rtc())
        for invalid in (bytes(16), b'2'*16, rtc(0x6a), rtc()[:-1]+b'\x01'):
            with self.subTest(raw=invalid), self.assertRaises(ValueError):
                saves.validate_gba_rtc(invalid)

    def test_raw_handheld_requires_explicit_paths_and_known_lengths(self):
        donor = self.root/'emulator'
        put(donor/'Roms/GBA/renamed.gba', (self.card/self.rel).read_bytes())
        put(donor/'Saves/GBA/renamed.srm', b'\x24'*8192)
        report = self.collect({'sources': [{'root': str(donor), 'format': 'raw-handheld', 'system': 'GBA',
                                            'roms': 'Roms/GBA', 'saves': 'Saves/GBA'}]})
        self.assertEqual(report['imports'], 1)
        put(donor/'Saves/GBA/renamed.rtc', bytes(48))
        self.assertEqual(self.collect({'sources': [{'root': str(donor), 'format': 'raw-handheld', 'system': 'GBA',
                                                    'roms': 'Roms/GBA', 'saves': 'Saves/GBA'}]})['conflicts'], 1)


class GameBoyProgress(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.card, self.inputs = self.root/'card', self.root/'inputs'
        put(self.card/'Analogue_Pocket.json', b'{"product":"Analogue Pocket"}')
        self.rel = 'Assets/gbc/common/中文目录/Fixture.gbc'
        self.old = 'Saves/gbc/common/中文目录/Fixture.sav'
        self.components = [{'id': 'GB-GBC', 'library': 'library'}]
        self.configure(0x1b)

    def configure(self, mapper, ram=3):
        raw = bytearray(32768)
        raw[0x143], raw[0x147], raw[0x149] = 0x80, mapper, ram
        put(self.card/self.rel, raw)
        ref = delivery.snapshot(self.card/self.rel, self.rel)
        self.target = 'Saves/gbclab/common/'+ref['sha256'][:20]+'.sav'
        delivery.write(self.inputs/'library/library-manifest.json', {'source_refs': [ref]})

    def collect(self, options=None):
        return saves.collect(self.card, self.components, self.inputs, options or {})

    def snapshot(self):
        return {p.relative_to(self.card).as_posix(): p.read_bytes()
                for p in self.card.rglob('*') if p.is_file()}

    def test_existing_ram_or_16_byte_trailer_is_kept_with_mapper_specific_warning(self):
        for mapper, ram, size in ((0x1b, 3, 32768), (0x1b, 2, 8192), (0x10, 3, 32768)):
            self.configure(mapper, ram)
            for extra in (0, 16):
                with self.subTest(mapper=mapper, ram=ram, extra=extra):
                    raw = b'\x53'*size + bytes(range(extra))
                    put(self.card/self.target, raw)
                    put(self.card/self.old, b'\x19'*(size+16 if mapper == 0x10 else size))
                    before = self.snapshot()
                    report, payloads = self.collect()
                    row = report['games'][0]
                    self.assertEqual(row['status'], 'keep_existing')
                    self.assertEqual(report['existing_preserved'], 1)
                    self.assertEqual((report['imports'], report['conflicts']), (0, 0))
                    self.assertEqual(payloads, {})
                    self.assertEqual(bool(row['errors']), mapper == 0x1b and extra == 16)
                    if row['errors']:
                        self.assertIn('16-byte trailer', row['errors'][0])
                        self.assertIn('no RTC', row['errors'][0])
                        self.assertIn(self.target, row['errors'][0])
                        self.assertEqual(report['existing_save_warnings'], 1)
                    self.assertEqual(report['existing_rtc_warnings'], 0)
                    self.assertEqual(self.snapshot(), before)

    def test_roms_without_any_donor_save_are_not_opened(self):
        native = self.root/'native-donor'
        raw = self.root/'raw-donor'
        put(native/'Analogue_Pocket.json', b'{"product":"Analogue Pocket"}')
        native_rom = native/'Assets/gbc/common/Renamed.gbc'
        raw_rom = raw/'Roms/GB/Renamed.gb'
        unrelated = self.card/'Assets/gb/common/Unplayed.gb'
        for path in (native_rom, raw_rom, unrelated):
            put(path, (self.card/self.rel).read_bytes())
        (raw/'Saves/GB').mkdir(parents=True)
        options = {'sources': [{'root': str(native)}, {'root': str(raw), 'format': 'raw-handheld',
                    'system': 'GB-GBC', 'roms': 'Roms/GB', 'saves': 'Saves/GB'}]}
        blocked = {native_rom, raw_rom, unrelated}
        original_open = Path.open
        def forbid_rom_read(path, *args, **kwargs):
            if path in blocked:
                raise PermissionError('Synthetic unsaved ROM must not be read')
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', new=forbid_rom_read):
            report, payloads = self.collect(options)
        self.assertEqual((report['imports'], report['conflicts']), (0, 0))
        self.assertEqual(payloads, {})

    def test_hash_named_donor_remains_a_candidate_and_rom_change_blocks_apply(self):
        donor = self.root/'donor'
        put(donor/'Analogue_Pocket.json', b'{"product":"Analogue Pocket"}')
        rom = donor/'Assets/gbc/common/Renamed.gbc'
        put(rom, (self.card/self.rel).read_bytes())
        put(donor/self.target, b'\x23'*32768)
        options = {'sources': [{'root': str(donor)}]}
        report, _ = self.collect(options)
        self.assertEqual(report['imports'], 1)
        self.assertEqual(report['games'][0]['candidates'][0]['save']['path'], self.target)

        stage, backup = self.root/'stage', self.root/'backup'
        stage.mkdir()
        parts = [('GB-GBC', {'identity': delivery.identity(self.card), 'changes': []})]
        saves.attach(self.card, self.components, self.inputs, stage, parts, options)
        delivery.seal(self.card, stage, parts)
        changed = bytearray(rom.read_bytes()); changed[-1] ^= 1
        rom.write_bytes(changed)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            delivery.apply(self.card, stage, backup)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(backup.exists())
        self.assertEqual((donor/self.target).read_bytes(), b'\x23'*32768)

    def test_existing_target_skips_unneeded_donor_rom_hashing(self):
        put(self.card/self.target, b'\x53'*32768 + bytes(range(16)))
        donor = self.root/'donor'
        put(donor/'Analogue_Pocket.json', b'{"product":"Analogue Pocket"}')
        rom = donor/'Assets/gbc/common/Renamed.gbc'
        put(rom, (self.card/self.rel).read_bytes())
        put(donor/'Saves/gbc/common/Renamed.sav', b'\x23'*32768)
        original_open = Path.open
        def forbid_donor_read(path, *args, **kwargs):
            if path == rom:
                raise PermissionError('Existing target needs no donor ROM read')
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', new=forbid_donor_read):
            report, payloads = self.collect({'sources': [{'root': str(donor)}]})
        self.assertEqual(report['existing_preserved'], 1)
        self.assertEqual(payloads, {})

    def test_other_existing_lengths_are_rejected_without_touching_files(self):
        for mapper in (0x1b, 0x10):
            self.configure(mapper)
            for size in (0, 8192, 32767, 32769, 32785):
                with self.subTest(mapper=mapper, size=size):
                    put(self.card/self.target, b'\x27'*size)
                    before = self.snapshot()
                    with self.assertRaisesRegex(ValueError, 'unexpected size'):
                        self.collect()
                    self.assertEqual(self.snapshot(), before)

    def test_non_rtc_native_and_raw_donor_trailers_are_not_imported(self):
        oversized = b'\x31'*32768 + bytes(range(16))
        put(self.card/self.old, oversized)
        before = self.snapshot()
        report, payloads = self.collect()
        self.assertEqual((report['conflicts'], report['imports']), (1, 0))
        self.assertEqual(payloads, {})
        self.assertFalse((self.card/self.target).exists())
        self.assertEqual(self.snapshot(), before)

        donor = self.root/'donor'
        put(donor/'Roms/GB/renamed.gb', (self.card/self.rel).read_bytes())
        put(donor/'Saves/GB/renamed.srm', oversized)
        options = {'same_card': False, 'sources': [{'root': str(donor), 'format': 'raw-handheld',
                   'system': 'GB-GBC', 'roms': 'Roms/GB', 'saves': 'Saves/GB'}]}
        report, payloads = self.collect(options)
        self.assertEqual((report['conflicts'], report['imports']), (1, 0))
        self.assertEqual(payloads, {})
        self.assertEqual((donor/'Saves/GB/renamed.srm').read_bytes(), oversized)
        put(donor/'Saves/GB/renamed.srm', oversized[:32768])
        report, payloads = self.collect(options)
        self.assertEqual((report['conflicts'], report['imports']), (0, 1))
        self.assertEqual(next(iter(payloads.values())), (oversized[:32768], None))
        self.assertFalse((self.card/self.target).exists())

    def test_existing_trailer_survives_real_prepare_install_and_rollback(self):
        # Use the real GB builder, adapter and transaction; only RBF identity is
        # synthetic. This does not exercise FPGA execution or hardware saves.
        package = self.inputs/'GB-GBC'
        repo = Path(__file__).resolve().parents[1]
        shutil.copytree(repo/'packaging', package/'core')
        binary = 'Cores/pocketlab.CoverFlow/gbc.rbf_r'
        put(package/'core'/binary, b'SYNTHETIC GB INSTALLER FIXTURE')
        accepted = delivery.sha(package/'core'/binary)
        delivery.write(package/'core/release-manifest.json', {'version': 'fixture', 'bitstream_sha256': accepted,
            'files': [delivery.snapshot(p, p.relative_to(package/'core').as_posix())
                      for p in (package/'core').rglob('*') if p.is_file()]})
        shutil.copytree(package/'core', self.card, dirs_exist_ok=True)
        bios = self.inputs/'bios.bin'
        put(bios, bytes(2304))
        original = self.inputs/'original'
        build_library.build(self.card, original, bios=bios)
        shutil.copytree(original/'Assets', self.card/'Assets', dirs_exist_ok=True)
        raw = b'\x53'*32768 + bytes(range(16))
        put(self.card/self.target, raw)
        put(self.card/self.old, b'\x19'*32768)
        put(self.card/'Saves/gba/common/MinishCap.sav', b'other important synthetic progress')

        titles = self.inputs/'titles.json'
        delivery.write(titles, {self.rel: '测试新标题'})
        build_library.build(self.card, self.inputs/'updated', titles=titles, bios=bios)
        config = self.inputs/'delivery.json'
        delivery.write(config, {'components': [{'id': 'GB-GBC', 'package': 'GB-GBC', 'library': 'updated'}],
                               'save_import': {}})
        before = self.snapshot()
        stage, backup = self.root/'stage', self.root/'backup'
        with patch.object(build_release, 'RBF_SHA', accepted):
            plan = delivery.prepare(self.card, config, stage)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(plan['changes'])
        self.assertFalse(any(c['path'].startswith('Saves/') for c in plan['changes']))
        report = delivery.read(stage/'save-import-report.json')
        self.assertEqual((report['existing_preserved'], report['existing_save_warnings']), (1, 1))
        self.assertEqual(report['existing_rtc_warnings'], 0)

        # Progress made after preparation must also survive the actual commit.
        latest = b'\x54'*32768 + bytes(reversed(range(16)))
        (self.card/self.target).write_bytes(latest)
        delivery.apply(self.card, stage, backup)
        self.assertEqual((self.card/self.target).read_bytes(), latest)
        self.assertEqual((backup/'progress'/self.target).read_bytes(), latest)
        played = b'\x55'*32768 + bytes(range(16))
        (self.card/self.target).write_bytes(played)
        delivery.rollback(self.card, backup, execute=True)
        expected = {**before, self.target: played}
        self.assertEqual(self.snapshot(), expected)


if __name__ == '__main__':
    unittest.main()
